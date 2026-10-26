#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Deserialize;
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Mutex,
    },
    time::{Duration, Instant},
};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::webview::{Cookie, NewWindowResponse};
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_opener::OpenerExt;

#[derive(Deserialize)]
struct Ready {
    protocol: u32,
    port: u16,
    nonce: String,
    pid: u32,
}

struct Backend {
    child: Child,
    #[cfg(windows)]
    job: Option<hutch_process_guard::windows::OwnedJob>,
}

#[derive(Default)]
struct HostState {
    backend: Mutex<Option<Backend>>,
    closing: AtomicBool,
}

#[derive(Default)]
struct HostOrigin(Mutex<Option<tauri::Url>>);

impl Backend {
    fn stop(&mut self) {
        if let Some(mut input) = self.child.stdin.take() {
            let _ = input.write_all(b"quit\n");
        }
        let deadline = Instant::now() + Duration::from_secs(15);
        while Instant::now() < deadline {
            if self.child.try_wait().ok().flatten().is_some() {
                #[cfg(windows)]
                self.job.take(); // close also ends any descendant left behind
                return;
            }
            std::thread::sleep(Duration::from_millis(50));
        }
        #[cfg(windows)]
        if let Some(job) = self.job.take() {
            let _ = job.terminate();
            drop(job); // kill-on-close still applies if explicit termination failed
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}

fn random_secret() -> String {
    rand::random::<[u8; 32]>()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn backend_command(app: &tauri::AppHandle) -> Result<Command, String> {
    if cfg!(debug_assertions) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap();
        let python = root.join(if cfg!(windows) {
            ".venv/Scripts/python.exe"
        } else {
            ".venv/bin/python"
        });
        let mut command = Command::new(python);
        command.args(["-m", "hutch.desktop"]);
        command.current_dir(root);
        Ok(command)
    } else {
        let resources = app
            .path()
            .resource_dir()
            .map_err(|_| "Could not locate Hutch resources".to_string())?;
        let helper = resources.join("backend").join(if cfg!(windows) {
            "hutch-backend.exe"
        } else {
            "hutch-backend"
        });
        Ok(Command::new(helper))
    }
}

fn parse_ready(line: &str, nonce: &str, pid: u32) -> Result<Ready, String> {
    if line.len() > 4096 {
        return Err("Hutch returned an oversized readiness message".to_string());
    }
    let ready: Ready = serde_json::from_str(line)
        .map_err(|_| "Hutch returned an invalid readiness message".to_string())?;
    if ready.protocol != 1 || ready.nonce != nonce || ready.pid != pid || ready.port == 0 {
        return Err("Hutch readiness did not match the launched process".to_string());
    }
    Ok(ready)
}

fn dashboard_digest(token: &str) -> String {
    hmac_sha256::HMAC::mac(token.as_bytes(), b"hutch-dashboard")
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn is_startup_url(url: &tauri::Url) -> bool {
    let local_host = (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (matches!(url.scheme(), "http" | "https") && url.host_str() == Some("tauri.localhost"));
    local_host && url.port().is_none() && url.username().is_empty() && url.password().is_none()
}

fn is_backend_url(url: &tauri::Url, backend: Option<&tauri::Url>) -> bool {
    url.username().is_empty()
        && url.password().is_none()
        && backend.is_some_and(|origin| url.origin() == origin.origin())
}

fn launch_backend(app: &tauri::AppHandle) -> Result<(Backend, Ready, String), String> {
    let token = random_secret();
    let nonce = random_secret();
    let mut command = backend_command(app)?;
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    let child = command
        .spawn()
        .map_err(|_| "The bundled Hutch backend could not start".to_string())?;
    let mut backend = Backend {
        child,
        #[cfg(windows)]
        job: None,
    };
    #[cfg(windows)]
    {
        // The trusted sidecar waits on stdin. Establish kernel ownership before
        // it receives permission to initialize the server or spawn workers.
        backend.job = Some(
            hutch_process_guard::windows::OwnedJob::attach_waiting_child(&backend.child)
                .map_err(|_| "Windows could not establish Hutch process ownership".to_string())?,
        );
    }
    let bootstrap = serde_json::json!({"token": token, "nonce": nonce});
    writeln!(backend.child.stdin.as_mut().unwrap(), "{bootstrap}")
        .map_err(|_| "The private startup handshake failed".to_string())?;
    let output = backend.child.stdout.take().unwrap();
    let (sender, receiver) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut line = String::new();
        let result = BufReader::new(output).take(4097).read_line(&mut line);
        let _ = sender.send(if result.is_ok() && line.len() <= 4096 {
            Some(line)
        } else {
            None
        });
    });
    let line = receiver
        .recv_timeout(Duration::from_secs(35))
        .ok()
        .flatten()
        .ok_or_else(|| {
            "Hutch did not become ready; check the local startup diagnostics".to_string()
        })?;
    let ready = parse_ready(&line, &nonce, backend.child.id())?;
    let digest = dashboard_digest(&token);
    Ok((backend, ready, digest))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .manage(HostState::default())
        .manage(HostOrigin::default())
        .setup(|app| {
            // Readiness is learned on a background thread; the startup window,
            // menu and Quit remain responsive if the backend fails to initialize.
            let navigation_app = app.handle().clone();
            let popup_app = app.handle().clone();
            let opener = app.handle().clone();
            let window =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                    .title("Hutch")
                    .inner_size(1180.0, 820.0)
                    .min_inner_size(360.0, 540.0)
                    .on_navigation(move |url| {
                        if is_startup_url(url) {
                            return true;
                        }
                        let state = navigation_app.state::<HostOrigin>();
                        let allowed = state.0.lock().ok().and_then(|origin| origin.clone());
                        is_backend_url(url, allowed.as_ref())
                    })
                    .on_new_window(move |url, _features| {
                        let state = popup_app.state::<HostOrigin>();
                        let allowed = state.0.lock().ok().and_then(|origin| origin.clone());
                        if is_backend_url(&url, allowed.as_ref()) {
                            return NewWindowResponse::Allow;
                        }
                        if url.scheme() == "https" {
                            let _ = opener.opener().open_url(url.to_string(), None::<&str>);
                        }
                        NewWindowResponse::Deny
                    })
                    .build()?;
            let show = MenuItem::with_id(app, "show", "Show Hutch", true, None::<&str>)?;
            let quit = MenuItem::with_id(
                app,
                "quit",
                "Quit Hutch and stop its work",
                true,
                None::<&str>,
            )?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            app.set_menu(menu.clone())?;
            let icon = app
                .default_window_icon()
                .cloned()
                .ok_or_else(|| std::io::Error::other("Hutch icon is missing"))?;
            TrayIconBuilder::new().icon(icon).menu(&menu).build(app)?;
            let host = app.handle().clone();
            std::thread::spawn(move || {
                let started = (|| -> Result<(), String> {
                    let (backend, ready, digest) = launch_backend(&host)?;
                    let state = host.state::<HostState>();
                    {
                        let mut owned = state
                            .backend
                            .lock()
                            .map_err(|_| "Hutch ownership state could not be verified")?;
                        if state.closing.load(Ordering::Acquire) {
                            return Ok(());
                        }
                        *owned = Some(backend);
                    }
                    let target: tauri::Url = format!("http://127.0.0.1:{}", ready.port)
                        .parse()
                        .map_err(|_| "Hutch returned an invalid local address")?;
                    *host
                        .state::<HostOrigin>()
                        .0
                        .lock()
                        .map_err(|_| "Hutch's local address could not be verified")? =
                        Some(target.clone());
                    window
                        .set_cookie(
                            Cookie::build(("hutch_auth", digest))
                                .domain("127.0.0.1")
                                .path("/")
                                .http_only(true)
                                .same_site(cookie::SameSite::Strict)
                                .build(),
                        )
                        .map_err(|_| "Hutch could not establish the private desktop session")?;
                    window
                        .navigate(target)
                        .map_err(|_| "Hutch could not open its local workspace")?;
                    Ok(())
                })();
                if let Err(error) = started {
                    let state = host.state::<HostState>();
                    if let Ok(mut owned) = state.backend.lock() {
                        owned.take();
                    }
                    if !state.closing.load(Ordering::Acquire) {
                        let message = serde_json::to_string(&format!(
                            "{error}. Quit and reopen Hutch to retry."
                        ))
                        .unwrap();
                        let _ = window.eval(format!(
                            "document.getElementById('startup-status').textContent = {message};"
                        ));
                        let _ = window.set_title("Hutch — startup needs attention");
                    }
                }
            });
            Ok(())
        })
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => app.exit(0),
            _ => (),
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("Hutch desktop could not start")
        .run(|app, event| {
            if matches!(event, RunEvent::ExitRequested { .. }) {
                if let Some(state) = app.try_state::<HostState>() {
                    state.closing.store(true, Ordering::Release);
                    if let Ok(mut backend) = state.backend.lock() {
                        backend.take();
                    }
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn readiness_is_bound_to_the_launched_process() {
        let good = r#"{"protocol":1,"port":48888,"nonce":"test-nonce","pid":123}"#;
        assert_eq!(parse_ready(good, "test-nonce", 123).unwrap().port, 48888);
        for wrong in [
            good.replace("test-nonce", "other-nonce"),
            good.replace("123", "124"),
            good.replace("48888", "0"),
            good.replace("48888", "65536"),
            good.replace("\"protocol\":1", "\"protocol\":2"),
            "[]".to_string(),
            "not json".to_string(),
            "x".repeat(4097),
        ] {
            assert!(parse_ready(&wrong, "test-nonce", 123).is_err());
        }
    }

    #[test]
    fn cookie_digest_matches_the_python_security_middleware() {
        assert_eq!(
            dashboard_digest("desktop-test-token"),
            "8221e046ee49c068c88ba8ace914880c2a88dd954188a69bb68db71e22957358"
        );
    }

    #[test]
    fn navigation_cannot_escape_the_owned_origin() {
        let backend = tauri::Url::parse("http://127.0.0.1:48888").unwrap();
        assert!(is_backend_url(
            &backend.join("/#/chat").unwrap(),
            Some(&backend)
        ));
        for value in [
            "http://127.0.0.1:48889",
            "http://localhost:48888",
            "https://127.0.0.1:48888",
            "http://user@127.0.0.1:48888",
            "file:///etc/passwd",
            "https://example.com",
        ] {
            assert!(!is_backend_url(
                &tauri::Url::parse(value).unwrap(),
                Some(&backend)
            ));
        }
        assert!(!is_backend_url(&backend, None));
        assert!(is_startup_url(
            &tauri::Url::parse("tauri://localhost/index.html").unwrap()
        ));
        assert!(is_startup_url(
            &tauri::Url::parse("http://tauri.localhost/index.html").unwrap()
        ));
        for value in [
            "tauri://untrusted/index.html",
            "http://tauri.localhost:7777",
            "http://tauri.localhost.example.com",
            "http://user@tauri.localhost",
            "file:///index.html",
        ] {
            assert!(!is_startup_url(&tauri::Url::parse(value).unwrap()));
        }
    }
}
