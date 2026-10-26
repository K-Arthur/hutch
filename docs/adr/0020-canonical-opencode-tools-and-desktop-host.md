# ADR 0020: canonical external-runtime tools and a private desktop host

Date: 2026-10-26. Status: canonical Linux tool bridge implemented and tested;
desktop host in development. This is not a cross-platform readiness claim.

## Decision

OpenCode's per-run bridge now dispatches admitted canonical Hutch tools through
the same `call_tool` path as the built-in runtime. Kernel peer identity remains
mandatory; Bot/run identity is never supplied by the client. Every call reloads
the owner fence, lease, cancellation state, enabled tools and current account
grants. The memory-only facade retains its existing constructor and plugin
contract. Generic requests are bounded to 128 KiB, replies to 64 KiB, and the
number of calls to the Bot's step limit. Receipts use distinct call positions.

Tools preserve their own policy and exact-action approval behavior. Closing the
bridge releases approval waits without starting an effect. Browser instances
remain on one bridge thread; account tools are reconstructed from fresh grants.
Native OpenCode write/shell/web alternatives are denied when the corresponding
capability is brokered. A document-only grant cannot enable arbitrary native
file edits. Native computer control and unmanaged delegation remain unavailable.
Visual tool results are recorded for the user; the text bridge explicitly says
that it has not transmitted their pixels to the model.

The built-in and OpenCode runtimes share instruction rendering, so rehearsal,
coordinator guidance, already-resolved skill context and persona plans do not
drift. This does not expand runtime skill eligibility or tool permissions.
Evidence guidance distinguishes observed facts, calculations, hypotheses and
unknowns. This addition was driven by reviewed live artifacts that inferred a
price advantage without a product price, profit from ROAS without costs, and
product fit from contact eligibility without an ICP. One early longer wording
crossed an existing 4,096-token context boundary; it was shortened and that
regression was checked without weakening the test.

## Native host boundary

The Tauri host owns a bundled Python sidecar. A bounded stdin/stdout protocol
binds readiness to a random nonce and the exact child PID. The backend binds an
already-owned ephemeral IPv4 loopback socket. The owner token travels through
stdin, never a URL or argument, and is removed from the backend environment
after constructing its security middleware. Native code installs an HttpOnly,
SameSite=Strict cookie in its webview. Normal server Host/origin/CSRF checks
remain active. No frontend filesystem, process or arbitrary-command IPC is
granted. Losing the host's pipe requests normal backend/worker shutdown.

Closing the window hides it; explicit Quit shuts down the owned backend. The
host adds single-instance behavior and native tray/menu controls. Rust is used
for native integration; no unmeasured speedup or Rust agent-loop replacement is
claimed. ADR 0016's performance requirement remains in force.

## Evidence and outstanding work

The installed OpenCode V2.1.4 plugin RPC wrote fixture files through the actual
canonical tool pipeline. Three free DeepSeek guide-derived local-artifact
evaluations passed independent arithmetic/suppression/receipt checks. Manual
artifact review identified the unsupported inferences above; the same fixtures
were rerun after shared guidance and the reviewed outputs marked those premises
unknown. These runs do not prove live-service integration parity, generalized
quality, repeated reliability, or comparative superiority over Grok Bot.

The Rust host passes build, three boundary tests and Clippy with warnings denied.
Six source/frozen-backend checks validate private readiness, authentication,
assets, malformed handshakes, an actual owned worker's file output and receipt,
and host-pipe shutdown. The first frozen startup failed on missing dependency
metadata; the packager now includes it recursively. This is a glibc 2.44 local
build, not an Ubuntu 24.04 installed-package result. Native GUI journeys, OS
keychains, Windows/macOS process and workspace boundaries, native peer
authentication, release signing and update recovery remain gates.
