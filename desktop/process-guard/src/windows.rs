//! An unnamed, non-inheritable kill-on-close Job Object. Assign only a trusted
//! child waiting on its private startup pipe, before releasing that handshake.
//! The OS captures later descendants without PID enumeration or reuse races.

use std::{
    io,
    os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
    process::Child,
};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, TerminateJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

pub struct OwnedJob {
    handle: OwnedHandle,
}

impl OwnedJob {
    pub fn attach_waiting_child(child: &Child) -> io::Result<Self> {
        // No name or inheritable SECURITY_ATTRIBUTES: unrelated processes cannot
        // keep this job alive by inheriting the host's handle.
        let raw = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if raw.is_null() {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: CreateJobObjectW returned a new uniquely owned CloseHandle handle.
        let handle = unsafe { OwnedHandle::from_raw_handle(raw) };
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let configured = unsafe {
            SetInformationJobObject(
                handle.as_raw_handle(),
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                std::mem::size_of_val(&limits) as u32,
            )
        };
        if configured == 0 {
            return Err(io::Error::last_os_error());
        }
        // Use the owned Child's process handle, never a caller-supplied PID.
        if unsafe { AssignProcessToJobObject(handle.as_raw_handle(), child.as_raw_handle()) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self { handle })
    }

    pub fn terminate(&self) -> io::Result<()> {
        if unsafe { TerminateJobObject(self.handle.as_raw_handle(), 1) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{BufRead, BufReader, Write},
        process::{Command, Stdio},
        sync::mpsc,
        time::Duration,
    };
    use windows_sys::Win32::{
        Foundation::{WAIT_OBJECT_0, WAIT_TIMEOUT},
        System::JobObjects::IsProcessInJob,
        System::Threading::{
            OpenProcess, WaitForSingleObject, PROCESS_QUERY_LIMITED_INFORMATION,
            PROCESS_SYNCHRONIZE,
        },
    };

    #[test]
    fn dropping_the_job_ends_root_and_later_descendants() {
        exercise_tree_termination(false);
    }

    #[test]
    fn explicit_termination_ends_root_and_later_descendants() {
        exercise_tree_termination(true);
    }

    fn exercise_tree_termination(explicit: bool) {
        // Python is a developer/test prerequisite, not an end-user dependency.
        // The fixture waits before it can spawn a descendant, exactly like the
        // trusted desktop backend's pre-bootstrap stdin boundary.
        let python = std::env::var("HUTCH_TEST_PYTHON").unwrap_or_else(|_| "python".into());
        let script = "import sys,subprocess;sys.stdin.readline();p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print(p.pid,flush=True);sys.stdin.readline()";
        let mut root = Command::new(python)
            .args(["-u", "-c", script])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("test Python must start");
        let job = match OwnedJob::attach_waiting_child(&root) {
            Ok(job) => job,
            Err(error) => {
                let _ = root.kill();
                let _ = root.wait();
                panic!("job ownership must be established: {error}");
            }
        };
        root.stdin.as_mut().unwrap().write_all(b"start\n").unwrap();
        let stdout = root.stdout.take().unwrap();
        let (sender, receiver) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut line = String::new();
            let result = BufReader::new(stdout).read_line(&mut line);
            let _ = sender.send(result.ok().map(|_| line));
        });
        let line = receiver
            .recv_timeout(Duration::from_secs(8))
            .expect("bounded fixture readiness")
            .expect("fixture must report a descendant");
        let pid = line.trim().parse::<u32>().unwrap();
        let raw = unsafe {
            OpenProcess(
                PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
                0,
                pid,
            )
        };
        assert!(!raw.is_null());
        // SAFETY: OpenProcess returned a new handle; hold it across death so a
        // reused numeric PID cannot make the assertion pass for another process.
        let descendant = unsafe { OwnedHandle::from_raw_handle(raw) };
        for handle in [root.as_raw_handle(), descendant.as_raw_handle()] {
            let mut belongs = 0;
            assert_ne!(
                unsafe { IsProcessInJob(handle, job.handle.as_raw_handle(), &mut belongs) },
                0
            );
            assert_ne!(
                belongs, 0,
                "both live processes must belong to this exact job"
            );
            assert_eq!(unsafe { WaitForSingleObject(handle, 0) }, WAIT_TIMEOUT);
        }
        if explicit {
            job.terminate()
                .expect("explicit job termination must succeed");
        } else {
            drop(job);
        }
        for handle in [root.as_raw_handle(), descendant.as_raw_handle()] {
            assert_eq!(unsafe { WaitForSingleObject(handle, 5000) }, WAIT_OBJECT_0);
        }
        // A signaled process handle proves termination. Kill-on-close is not
        // specified to produce a failing Rust ExitStatus; the native run returned
        // status zero. Explicit TerminateJobObject uses our requested code instead.
        let status = root.wait().unwrap();
        if explicit {
            assert_eq!(status.code(), Some(1));
        }
    }
}
