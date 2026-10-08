# Acceptance tests

Test IDs referenced by the evidence ledger and ADRs. "Offline" means it runs in the normal suite with no network, model or
browser. "Live" means it needs something this host did not have and is skipped with a stated reason, never counted as passed.

| ID | Invariant | Kind | File | Status |
|---|---|---|---|---|
| T-CRED-SCOPE | A key is never sent to a host it does not belong to | offline | `tests/test_credential_routing.py` | passing |
| T-SSRF | No URL form, redirect or DNS answer reaches a private address | offline | `tests/test_netguard.py` | passing |
| T-CLAIM-RACE | Two processes racing for the same pending run: exactly one claim wins | offline (multiprocess) | `tests/test_claims.py` | passing |
| T-OCCURRENCE-RACE | Two schedulers for one occurrence create one run, also after a crash between steps | offline (multiprocess) | `tests/test_claims.py` | passing |
| T-STATE-MACHINE | Only table transitions are possible; terminal is absorbing; stale fence rejected | offline (property) | `tests/test_lifecycle.py` | passing |
| T-SHELL-READABLE | Readable command contexts preserve policy; ambiguous syntax fails closed rather than being assumed benign | offline (property) | `tests/test_shellparse.py` | passing |
| T-MIGRATION-V8 | A v4 database with data migrates and backs up; ids, events, schedules survive; each historic run is imported separately | offline | `tests/test_migration.py` | passing |
| T-CROSS-PROCESS-STOP | `stop` from process B ends a run owned by process A | offline (multiprocess) | `tests/test_cancel.py` | passing |
| T-CANCEL-DESCENDANTS | After terminal cancel no descendant process is alive and none can write | offline | `tests/test_procguard.py` | passing |
| T-RECEIPT-RECOVERY | Crash after an effect but before its receipt ends `outcome_unknown` and is never replayed | offline | `tests/test_receipts.py` | passing |
| T-APPROVAL-CAS | Two clients resolve one approval: exactly one wins; a revised action needs a new approval | offline | `tests/test_approval_cas.py` | passing |
| T-SANDBOX | The shell cannot read the real home or open a socket without a grant; unsupported host fails closed | offline (skips without bwrap) | `tests/test_sandbox.py` | passing on this Linux host |
| T-ADAPTER-CONTRACT-OPENCODE | OpenCode argv/event parsing matches the installed binary | offline fixtures + live-if-installed | `tests/test_runtime_opencode.py` | planned |
| T-ADAPTER-CONTRACT-PI | Pi framing matches the published protocol; completion is `agent_settled` | offline fixtures | `tests/test_runtime_pi.py` | planned |
| T-PERMISSION-BROKER | OpenCode permission requests go through the Hutch approval gate | live-if-installed | `tests/test_runtime_opencode.py` | planned |
| T-COMPAT-MATRIX | Every route has state, evidence URL and date; unsupported fields are stripped | offline | `tests/test_compat.py` | planned |
| T-PROVIDER-FIELD-REJECT | A provider rejection (auth, quota, field) leaves a recoverable state and no paid fallback | offline | `tests/test_provider_failures.py` | planned |
| T-NO-SILENT-FALLBACK | Falling to another billing relationship needs approval | offline | `tests/test_provider_failures.py` | planned |
| T-RESERVE | Parallel runs cannot over-reserve a shared budget | offline | `tests/test_reservations.py` | planned |
| T-STRICT-OFFLINE | Offline mode makes no non-loopback connection and refuses cloud-backed Ollama | offline | `tests/test_offline_mode.py` | planned |
| T-ADMISSION | Admission waits or refuses by memory; approval waits release the slot | offline | `tests/test_admission.py` | planned |
| T-CONVERSATION | Bounded follow-up context, isolated legacy import, idempotent create/message/archive, FTS search and restart persistence | offline | `tests/test_conversations.py`, `tests/test_migration.py` | partial; artifact/runtime-switch context not implemented |
| T-DELETE-SEMANTICS | Archive hides but retains a conversation; scoped delete/export remain unimplemented | offline | `tests/test_conversations.py` | partial |
| T-IDEMPOTENCY | Same key + request maps to the same result; changed request conflicts; retry survives restart | offline | `tests/test_conversations.py` | passing for conversation commands only |
| T-BROWSER-ISOLATION | Two bots never share profile, page or teardown | offline (fake driver) + live-if-Playwright | `tests/test_browser_ownership.py` | planned |
| T-HANDOFF | `waiting_human` pauses automation and resumes after revalidation | offline (fake driver) | `tests/test_browser_ownership.py` | planned |
| T-INJECTION | Tool-result text cannot add authority or become executable UI | offline | `tests/test_untrusted_content.py` | planned |
| T-DELEGATION | Depth, fan-out, cycle and budget limits hold | offline | `tests/test_delegation.py` | planned |
| T-PAIRING | Pairing code is single-use under race, expired/replayed codes fail, IP attempts throttle, device session revokes, explicit remote bind requires TLS | offline fixtures | `tests/test_remote_pairing.py` | passing; no physical device/network test |
| T-HOST-SLEEP | Offline/queued state is reported honestly after the host was suspended | offline | `tests/test_cancel.py` (lease lapse, fenced zombie) | passing |
| T-WORKER-PROCESS | A run executes in its own session; Stop, SIGKILL, a frozen worker and a dead supervisor are all handled | offline (real processes) | `tests/test_worker.py` | passing |
| T-EVENT-CHAIN | Several processes writing one transcript keep one unbroken chain; a zombie is refused at the database | offline (real processes) | `tests/test_claims.py` | passing |
| T-RECEIPT-SEMANTICS | An intent brackets the effect, not an approval wait; a refused or denied action has no receipt | offline | `tests/test_receipts.py` | passing |
| T-PERF-BUDGET | Control-plane regression budgets hold against the pre-change baseline | offline | `benchmarks/run.py --check`, `benchmarks/quality_audit.ipynb` | captured on this host; CLI p50 is about 5% slower, event throughput higher, mock step overhead lower; see raw samples and limits |
