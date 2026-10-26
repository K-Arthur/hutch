# Hutch native desktop host

Development preview, not a published desktop release. The Rust/Tauri host owns the
existing Python server; it does not replace the agent loop or claim a speedup.

## Current evidence

On the development Linux host, the native host builds, passes three Rust boundary
tests, and passes Clippy with warnings denied. Source and frozen backends pass
readiness, authentication, asset, malformed-input, owned-worker, file-effect,
receipt and host-loss checks. The first frozen startup exposed missing XlsxWriter
metadata; the spec now includes dependency metadata recursively.

The frozen check was built with Python 3.13.15, PyInstaller 6.22.3 and glibc 2.44.
It is not an Ubuntu 24.04 compatibility result. The native GUI, installed package,
tray behavior and WebKit cookie/navigation journey still need actual validation.
Windows/macOS execution and workspace/process/IPC boundaries remain unported.
No signing, notarization, updater or public download is enabled.

## Develop

From the repository root, with the native prerequisites in the
[Tauri documentation](https://v2.tauri.app/start/prerequisites/):

```sh
uv sync --frozen --extra dev --extra browser --extra desktop
cargo test --locked --manifest-path desktop/Cargo.toml
cargo clippy --locked --manifest-path desktop/Cargo.toml --all-targets -- -D warnings
cargo run --locked --manifest-path desktop/Cargo.toml
```

Debug builds use this checkout's `.venv`. Release builds locate the frozen backend
under the app's resource directory, rather than assuming it is next to the native
executable (which is wrong for macOS bundles and some Linux packages).

The startup window opens before backend readiness. Close hides it; reopening the
app focuses the existing window. **Quit Hutch and stop its work** closes the host
pipe, requests normal server/worker shutdown, and has a bounded kill fallback.
An error remains visible in the startup window instead of crashing setup.

## Freeze and verify the backend

```sh
uv run --frozen --no-sync python scripts/build_desktop_backend.py
HUTCH_FROZEN_BACKEND="$PWD/desktop/binaries/backend/hutch-backend" \
  uv run --frozen --no-sync pytest -q tests/test_desktop_sidecar.py
```

Build on each target OS. The script refuses an existing `output/backend` so earlier
build evidence is preserved; `--output /path/to/fresh-output` chooses another root.
PyInstaller's one-directory output includes the Python runtime, internal worker
entry points, package resources and dependency metadata. It does not bundle model
weights, the OpenCode CLI, Playwright browser executables, LibreOffice, or every
host-native document renderer. Missing optional tools must retain their existing
unavailable states.

`tauri.bundle.conf.json` is a Linux-only packaging overlay that maps the complete
backend directory to `backend/` resources. With the Tauri CLI installed, build from
`desktop/` using `cargo tauri build --config tauri.bundle.conf.json`. This recipe
is not an installed-package validation result. Default `tauri.conf.json` keeps
bundling disabled. Windows/macOS package overlays follow their runtime ports and
native runner checks; merely adding those package targets is insufficient.

## Boundary and source provenance

Readiness is bounded and tied to the launched PID and a fresh nonce. The temporary
owner token goes through stdin and is removed before workers launch. No token goes
into a URL, command argument or readiness message. The webview receives only an
HttpOnly SameSite Strict cookie. Its frontend has no native shell/filesystem/command
IPC grants. Navigation stays within the owned backend or packaged startup origin;
external HTTPS links open in the system browser.

Tauri and its plugins are pinned in `Cargo.toml`/`Cargo.lock`; PyInstaller is pinned
in the optional `desktop` extra and Python lockfile. Host code is original Hutch
implementation. `icons/icon.svg` reproduces the existing Hutch hexagon/circle mark
from `src/hutch/server/static/index.html`; PNG/ICO/ICNS are packaging renditions of
that vector. No Hermes IDE code or competitor artwork was copied.

See [ADR 0020](../docs/adr/0020-canonical-opencode-tools-and-desktop-host.md) and the
[production checkpoint](../docs/realignment/desktop-production-2026-10-26.md) for
remaining acceptance and test evidence.

## Publisher OAuth registrations

Account authorization should open the signed-in system browser; end users do not register
Hutch in a Cloud console. The development `src/hutch/data/oauth-apps.json` intentionally has
empty public application IDs. Supply an independently registered Google Desktop app and/or
Microsoft public-client app when preparing a build:

```sh
uv run python scripts/build_desktop_backend.py --output /path/to/fresh-build \
  --oauth-apps /path/to/public-oauth-apps.json --require-oauth google microsoft
```

The input shape is `{"version":1,"apps":{"google":{"client_id":"…apps.googleusercontent.com"},"microsoft":{"client_id":"UUID"}}}`.
It accepts only public IDs, rejects secret/token fields and oversized files, and replaces the
empty packaged manifest. `--require-oauth` refuses a missing registration before packaging.
This gate checks configuration, not ownership, live consent, verification or provider approval;
those remain release checks. Runtime operator overrides remain available. No third-party app
registration or browser credentials are borrowed.
