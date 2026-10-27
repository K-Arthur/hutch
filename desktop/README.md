# Hutch native desktop host

Development preview, not a published desktop release. The Rust/Tauri host owns the
existing Python server; it does not replace the agent loop or claim a speedup.

## Current evidence

On the development Linux host, the native host builds, passes three Rust boundary
tests, and passes Clippy with warnings denied. Source and frozen backends pass
readiness, authentication, asset, malformed-input, owned-worker, file-effect,
receipt and host-loss checks. The first frozen startup exposed missing XlsxWriter
metadata; the spec now includes dependency metadata recursively.

The original local frozen check used Python 3.13.15, PyInstaller 6.22.3 and glibc 2.44.
Separately, Ubuntu 24.04 hosted validation now builds the Debian/AppImage packages,
installs the Debian package, and passes ten actual source/frozen sidecar and worker checks.
The first installed webview check stopped on an unsupported test-driver argument;
its corrected rerun is pending. No native GUI or tray acceptance is claimed yet.
Actual four-host primitive validation passed on Ubuntu, Windows Server 2025,
macOS 14 arm64 and macOS 15 Intel: process locks, Windows Job Objects,
Unix group supervision and Windows/macOS native-vault roundtrips. See the
[source-bound evidence](../docs/realignment/artifacts/desktop-production-2026-10-26/native-boundaries-fe55b94f.json).
Python worker execution, workspace and peer-identity boundaries remain unported
on Windows/macOS. Packaged vault identity, restart and sleep/wake remain unverified.
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

On Linux/macOS the trusted sidecar starts in a distinct POSIX process group before exec. The Rust owner keeps its Child private, observes exit with `waitid(...WNOWAIT)`, signals the original group before reaping, and can terminate the exact root if it changes groups. This avoids signalling a recycled group after a root wait. Five real Unix tests cover inherited children, graceful/forced exit, sibling isolation, moved roots and spawn failure on Linux and both native macOS runners. Group supervision is lifecycle cleanup, not a sandbox or coverage of detached descendants. Linux containment remains in place; unsupported Windows/macOS advanced tools stay unavailable. The graceful wait is 15 seconds, followed by termination and a bounded five-second exit-confirmation wait; an unconfirmed exit is reported, not treated as verified cleanup. An error-path Drop may retry termination. `libc` 0.2.190 is pinned in both Rust lockfiles (MIT OR Apache-2.0); it was already a transitive desktop dependency.

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

## Native boundary CI

[Native platform boundaries](../.github/workflows/native-platform.yml) is a manual
matrix of standard GitHub-hosted Ubuntu 24.04 x64, Windows Server 2025 x64,
macOS 14 arm64 and macOS 15 Intel machines. Two workers run concurrently, with
15-minute deadlines. Repository visibility must be public before any matrix job
runs; skipped jobs are not acceptance evidence. No paid private-hosted fallback,
self-hosted setup or runner registration is required. The user asked Hutch's
implementation work to handle CI provisioning and confirmed no existing runners.

The host recorder validates OS, architecture, 64-bit Python and minimum Linux/macOS
versions, instead of trusting an image label. Checks exercise native kernel locks,
concurrent skills writes, Windows/macOS synthetic credential roundtrips and the
real Windows Job Object test. Host/source identity, JUnit and bounded Rust evidence
are emitted in job logs, which [do not use artifact-storage quota](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
No Actions artifact upload, cache or signing/publication authority is granted by
this native workflow. Actions are pinned to verified commit IDs, toolchains are
explicit and Python dependencies use the frozen lockfile.

The main Python/browser CI is also public-only, uses frozen dependencies and
explicit read permissions, and can be dispatched manually after the transition.
Its existing small benchmark cache is retained for real regression comparisons;
benchmark evidence goes to logs. The repository cache is currently 1,237 bytes,
within GitHub's documented per-repository included cache allowance. No quota or
account spending setting was changed.

Windows Server and macOS 15 Intel checks do not replace Windows 11/macOS 14 Intel
installed-app validation. Unix has no process-supervision tests in the small Rust
crate yet. Source/history/license review precedes the planned public transition;
missing native results remain explicit release blockers.

### Renderer dependencies and startup

Document generators load per format. Missing native PDF graphics libraries must not
prevent the backend, locks, credential store or other document formats from starting.
`GET /api/v1/documents/readiness` reports an unavailable format and its dependency reason;
a PDF request fails explicitly without changing format or promoting an artifact. This is
not a replacement for bundling and testing Pango/GLib and fonts on each target OS. The
current preview remains gated on complete native dependency packaging and installed tests.

### Public download manifest

`website/downloads.json` is contract v1 for the preview channel. Its four platform
entries are release targets; all artifact lists are empty because no installers have
been published. The marketing page links to the public source and Linux source setup,
not fabricated installer URLs. Only add an actual release artifact after its native
installed checks, checksum and dependency/license inventory are available; production
promotion also needs signing/notarization, safe update recovery and live acceptance.


## Installed Ubuntu validation

The manual `.github/workflows/desktop-linux.yml` workflow builds on Ubuntu 24.04,
freezes the Python backend, runs source/frozen sidecar and worker checks, and
builds both unsigned `.deb` and AppImage files. It installs the exact Debian
artifact, then drives that installed app and the exact AppImage in a real
WebKit webview under an isolated D-Bus/Xvfb session. AppImage uses its documented
extract-and-run runtime; this does not validate a FUSE mount. No account keys,
personal browser profiles, model calls or embedded test-control plugin are used.

The opt-in `tests/native/test_desktop_webdriver.py` requires
`HUTCH_DESKTOP_BINARY`, `tauri-driver` 2.1.0 and the OS `WebKitWebDriver`.
It checks private first-run startup, the HttpOnly owner cookie, unauthenticated
external-client refusal, real Apps & AI navigation and separate Google services.
It records a screenshot for later visual inspection and verifies cleanup of its
owned driver process tree. The local host lacks WebKitWebDriver, so the native
journey is unverified until that workflow actually passes; a skipped local check
is not acceptance. Tray/menu, sleep/wake and native worker containment remain
separate checks. See [Tauri's native-driver setup](https://v2.tauri.app/develop/tests/webdriver/manual-setup/).

`record_desktop_build.py` hashes the actual two package files, records their
source revision and inventories installed Python and resolved Linux Rust license
metadata. It refuses missing/duplicate formats and escaped/symlinked package
files, and flags missing/truncated license metadata for review. This build
inventory includes development dependencies; it is not an exact binary SBOM or
a completed native-library/license review. The workflow publishes no release,
uploads no Actions artifacts, uses no signing credentials and does not activate
download links. Passing build/install tests alone does not make Hutch production
ready or make Windows/macOS packages available.
