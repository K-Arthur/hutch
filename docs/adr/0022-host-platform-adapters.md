# 0022 — Host platform adapters and native evidence

Status: implementation in progress (2026-10-26). Extends ADR 0004 and ADR 0020.

## Decision

Put OS-specific primitives under `hutch.platforms`. Preserve the existing Linux
process/containment guarantees. A working primitive does not authorize a fallback
executor, weaken workspace checks or imply that a target OS release is validated.
Unsupported higher-level operations remain unavailable until their own port and
native regression evidence exist.

### File-lock contract v1

The migration, credential-rotation, transcript, workspace-write and upload callers
use the shared locking adapter. Unix delegates to the exact existing `fcntl.flock`
function and constants. Windows uses `LockFileEx`/`UnlockFileEx` against synchronous
CRT file handles, with exclusive/shared/nonblocking/unlock operations over the full
file range. Contention maps to `BlockingIOError`; handle close/process exit releases
kernel ownership. The adapter neither changes the file pointer nor replaces kernel
exclusion with PID files. Arbitrary fcntl operations and lock upgrades are outside
this subset. No additional dependency or Rust performance claim is introduced.

The same subprocess tests run on each OS: exclusive exclusion, shared-reader versus
writer exclusion, no content/position modification, and release after holder death.
Linux checks are local evidence. The Windows implementation remains unverified on
Windows until a native runner executes those tests. Merely importing the adapter,
mocking Win32 calls or cross-compiling does not satisfy that gate.

## Remaining platform work

Owned process-tree cancellation (Windows Job Objects and macOS supervision),
race-resistant workspace access including junctions/reparse points, platform secure
credential storage, local IPC and native background/sleep behavior need their own
explicit adapters and evidence. Native packaging gates must reflect these states;
do not mark Windows/macOS execution supported based only on removing Unix imports.

## Sources and provenance

Original Hutch implementation based on the published
[LockFileEx contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex),
[UnlockFileEx contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-unlockfileex),
and [Python flock contract](https://docs.python.org/3/library/fcntl.html).
No upstream implementation code was copied.


### Windows desktop owner contract v1

The Rust `hutch-process-guard` crate owns an unnamed, non-inheritable Job Object
with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. The desktop host assigns its owned
Child handle before sending the sidecar's private startup handshake. Later
children inherit job membership; breakaway is not enabled. Setup failure closes
the job and stops the still-unbootstrapped child. Quit requests graceful Python
shutdown first, with native job termination/close as the fallback. Job close also
cleans descendants left after the root has exited. Numeric PID enumeration is not
used for termination.

The crate is separate from WebKit/Tauri so its real Win32 code and test targets can
be type-checked from the development host. The Windows native test holds a
verified process handle across descendant death and verifies kill-on-close for a
root and a child spawned after assignment. Cross-check/Clippy are not execution
of that test; a Windows runner remains required. This does not port the Python
worker engine, secure workspace operations or credentials by itself. Rust is used
for required native ownership, not a measured Python speed replacement.

Sources: [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[assignment requirements](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject),
[Rust owned handles](https://doc.rust-lang.org/std/os/windows/io/struct.OwnedHandle.html).

The skill registry now uses the same kernel lock adapter rather than silently omitting
exclusion when `fcntl` is unavailable. Unlock errors still close the owned handle,
allowing kernel cleanup and preventing a stuck registry lock. Linux cross-process
registry contention and handle-error cleanup are exercised together with the existing
skills/API suites; native Windows execution remains outstanding.

### Native credential contract v1

Google file/Calendar/Gmail and Notion stores, plus Microsoft Calendar/Mail stores,
select Windows Credential Manager or macOS Keychain on those systems. Linux keeps
its existing Secret Service CLI protocol. Values go through native APIs, never
command arguments, SQLite, browser storage or fallback files. Errors omit backend
arguments. Disconnect is idempotent only after a successful missing lookup;
unavailable/locked stores do not become silently empty credentials.

The adapter directly selects the pinned native keyring class. It never invokes
backend discovery or loads the operator's keyring config, `KEYRING_PROPERTY_*`,
`KEYCHAIN_PATH` or `PYTHON_KEYRING_BACKEND` choices. Constructors explicitly choose
local per-user Windows persistence (no enterprise roaming) and the default macOS
keychain. Each native service target includes its account reference: the Windows
backend's service-level relocation cannot overwrite a different account during
concurrent sign-ins. No unrelated credentials are enumerated or imported.

Dependency: **keyring 25.7.0**, conditional on Windows/macOS. Verified the published
wheel's SHA-256 against PyPI and read its included MIT license before integration:
`be4a0b195f149690c166e850609a477c532ddbfbaed96a404d4e43f8d5e2689f`.
Use is through the library, not copied implementation code. Source/API:
[keyring v25.7.0](https://github.com/jaraco/keyring/tree/v25.7.0),
[Windows backend](https://github.com/jaraco/keyring/blob/v25.7.0/keyring/backends/Windows.py),
[macOS backend](https://github.com/jaraco/keyring/blob/v25.7.0/keyring/backends/macOS/__init__.py).
The lockfile records its conditional transitive dependencies; frozen target builds
explicitly include the selected native module and dependency license metadata.

Linux contract tests use a synthetic vault to verify routing, namespace separation,
error redaction and no subprocess/fallback. They are not Windows/macOS execution.
Native CI contains a real synthetic credential roundtrip, update, deletion and
idempotent disconnect; it must run on each OS. OS vault quotas, locked/cancelled
prompts, packaged-app access identity and restart behavior remain native validation
requirements. This adapter does not port POSIX private-file operations or enable
the unsupported Windows/macOS worker engine.

### Wake acceleration on unsupported transports

Windows exposes `AF_UNIX` but does not provide the Unix datagram transport used by
WakeHub. An unavailable accelerator must not attempt POSIX directory descriptors or
relax their security checks. It now creates no socket/directory, returns unavailable
from listen, and preserves the existing in-process notifications and waiter safety
timeouts. `/api/v1/capabilities` discloses this gap. This is startup isolation, not a
Windows native IPC implementation; native cross-process acceleration remains a release
porting requirement. Unix ownership, symlink refusal and mode checks stay unchanged.
