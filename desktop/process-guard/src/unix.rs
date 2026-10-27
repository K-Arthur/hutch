//! Supervise the trusted sidecar's inherited POSIX process group.
//!
//! This is lifecycle cleanup, not a sandbox: a process that creates another
//! session/group can escape. Keep Linux's existing worker containment and do
//! not advertise unsupported native execution as contained on macOS.
//!
//! The Child stays private and unreaped until group signalling finishes.
//! WNOWAIT observes exit while retaining the kernel PID reservation, so this
//! code never signals a numeric group after releasing its root identity.

use std::{
    io,
    os::unix::process::CommandExt,
    process::{Child, ChildStdin, ChildStdout, Command, ExitStatus},
    time::{Duration, Instant},
};

pub struct OwnedProcess {
    child: Child,
    pub stdin: Option<ChildStdin>,
    pub stdout: Option<ChildStdout>,
    finished: Option<ExitStatus>,
}

impl OwnedProcess {
    pub fn spawn(command: &mut Command) -> io::Result<Self> {
        // setpgid happens before exec, without a parent-side assignment race.
        let mut child = command.process_group(0).spawn()?;
        Ok(Self {
            stdin: child.stdin.take(),
            stdout: child.stdout.take(),
            child,
            finished: None,
        })
    }

    pub fn id(&self) -> u32 {
        self.child.id()
    }

    pub fn has_exited(&self) -> io::Result<bool> {
        if self.finished.is_some() {
            return Ok(true);
        }
        // SAFETY: zero initialization is valid for this OS output structure;
        // waitid writes it before it is read. This private Child cannot be
        // reaped elsewhere, and WNOWAIT keeps it reserved after observation.
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        loop {
            let result = unsafe {
                libc::waitid(
                    libc::P_PID,
                    self.id(),
                    &mut info,
                    libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
                )
            };
            if result == 0 {
                return Ok(unsafe { info.si_pid() } != 0);
            }
            let error = io::Error::last_os_error();
            if error.kind() != io::ErrorKind::Interrupted {
                return Err(error);
            }
        }
    }

    pub fn stop(&mut self, grace: Duration) -> io::Result<ExitStatus> {
        if let Some(status) = self.finished {
            return Ok(status);
        }
        // Closing the private input is the host-loss signal; callers may first
        // write their own graceful quit protocol through this same pipe.
        self.stdin.take();
        let deadline = Instant::now() + grace;
        while !self.has_exited()? && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(10));
        }
        // The unreaped direct child still reserves this number even after it
        // exits or changes its own group. No other root can reuse it as a PGID.
        let group = self.id() as libc::pid_t;
        let result = unsafe { libc::kill(-group, libc::SIGKILL) };
        if result != 0 {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ESRCH) {
                return Err(error);
            }
        }
        // A trusted root may have moved itself out of the inherited group.
        // Its private unreaped Child still owns the PID; end that exact root
        // without ever signalling its new (possibly unrelated) process group.
        if !self.has_exited()? {
            self.child.kill()?;
        }
        let kill_deadline = Instant::now() + Duration::from_secs(5);
        while !self.has_exited()? {
            if Instant::now() >= kill_deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "sidecar exit could not be confirmed after termination",
                ));
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let status = self.child.wait()?;
        self.finished = Some(status);
        Ok(status)
    }
}

impl Drop for OwnedProcess {
    fn drop(&mut self) {
        let _ = self.stop(Duration::ZERO);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{BufRead, BufReader, Read},
        process::Stdio,
        sync::mpsc::{self, Receiver},
    };

    fn fixture(ignore_input: bool) -> (OwnedProcess, Receiver<()>) {
        let python = std::env::var("HUTCH_TEST_PYTHON").unwrap_or_else(|_| "python3".into());
        let script = format!(
            "import os,sys,subprocess,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdin=subprocess.DEVNULL); print(str(os.getpid())+' '+str(os.getpgrp())+' '+str(os.getpgid(p.pid)),flush=True); {}",
            if ignore_input { "time.sleep(60)" } else { "sys.stdin.readline()" }
        );
        let mut owner = OwnedProcess::spawn(
            Command::new(python)
                .args(["-u", "-c", &script])
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null()),
        )
        .expect("fixture Python must start");
        let mut output = BufReader::new(owner.stdout.take().unwrap());
        let (ready_sender, ready) = mpsc::sync_channel(1);
        let (eof_sender, eof) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut line = String::new();
            output.read_line(&mut line).unwrap();
            ready_sender.send(line).unwrap();
            let mut tail = Vec::new();
            output.read_to_end(&mut tail).unwrap();
            let _ = eof_sender.send(());
        });
        let line = ready.recv_timeout(Duration::from_secs(8)).unwrap();
        let ids: Vec<u32> = line
            .split_whitespace()
            .map(|part| part.parse().unwrap())
            .collect();
        assert_eq!(
            ids,
            vec![owner.id(); 3],
            "root and child inherit this exact private group"
        );
        (owner, eof)
    }

    #[test]
    fn graceful_root_exit_retains_identity_until_descendant_cleanup() {
        let (mut owner, eof) = fixture(false);
        owner.stdin.take();
        let until = Instant::now() + Duration::from_secs(5);
        while !owner.has_exited().unwrap() && Instant::now() < until {
            std::thread::sleep(Duration::from_millis(10));
        }
        assert!(owner.has_exited().unwrap());
        let status = owner.stop(Duration::from_secs(1)).unwrap();
        assert!(status.success());
        eof.recv_timeout(Duration::from_secs(5))
            .expect("no inherited writer may survive");
        assert_eq!(owner.stop(Duration::ZERO).unwrap(), status);
    }

    #[test]
    fn deadline_ends_uncooperative_root_and_inherited_descendant() {
        let (mut owner, eof) = fixture(true);
        let started = Instant::now();
        assert!(!owner.stop(Duration::from_millis(30)).unwrap().success());
        assert!(started.elapsed() < Duration::from_secs(5));
        eof.recv_timeout(Duration::from_secs(5)).unwrap();
    }

    #[test]
    fn dropping_one_group_does_not_end_another() {
        let (first, first_eof) = fixture(true);
        let (mut second, second_eof) = fixture(true);
        assert_ne!(first.id(), second.id());
        drop(first);
        first_eof.recv_timeout(Duration::from_secs(5)).unwrap();
        assert!(!second.has_exited().unwrap());
        assert!(matches!(
            second_eof.try_recv(),
            Err(mpsc::TryRecvError::Empty)
        ));
        second.stop(Duration::ZERO).unwrap();
        second_eof.recv_timeout(Duration::from_secs(5)).unwrap();
    }

    #[test]
    fn missing_executable_never_creates_an_owner() {
        assert!(OwnedProcess::spawn(&mut Command::new("/hutch-test-no-such-executable")).is_err());
    }

    #[test]
    fn moved_root_is_ended_without_signalling_its_new_group() {
        let python = std::env::var("HUTCH_TEST_PYTHON").unwrap_or_else(|_| "python3".into());
        let mut owner = OwnedProcess::spawn(
            Command::new(python)
                .args(["-u", "-c", "import os,time; os.setpgid(0,os.getpgid(os.getppid())); print('moved',flush=True); time.sleep(60)"])
                .stdout(Stdio::piped())
                .stderr(Stdio::null()),
        ).unwrap();
        let mut output = BufReader::new(owner.stdout.take().unwrap());
        let (sender, receiver) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut line = String::new();
            output.read_line(&mut line).unwrap();
            let _ = sender.send(line);
        });
        assert_eq!(
            receiver.recv_timeout(Duration::from_secs(5)).unwrap(),
            "moved\n"
        );
        assert!(!owner.stop(Duration::ZERO).unwrap().success());
        // The test process shares the root's new group. Reaching here also
        // demonstrates that cleanup never signalled that unrelated group.
    }
}
