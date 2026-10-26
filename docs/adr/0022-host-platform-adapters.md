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
