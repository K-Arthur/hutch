# Edge cases and gaps the owner did not list

Check each at design time and again at review. For every row, either a test exists (name it in
`02-PROGRESS.md`), or the row is logged as deferred with a reason. Rows are grouped by area.

## Sign-in and sessions

| Case | Expected behavior |
|---|---|
| Passkey lost, only passkey | Local owner on loopback keeps access; remote sign-in has a documented recovery path; removing the last passkey is refused until another path is confirmed |
| Synced passkeys (iCloud, Google, 1Password) report counter 0 | Accepted; counters enforced only when the authenticator uses them (existing behavior, keep tested) |
| Hostname or RP ID changed (new domain, Tailscale rename) | Clear error naming the expected and actual origin; doctor check; old passkeys listed as "bound to old host", not silently dead |
| Reverse proxy strips or rewrites `Origin` / forwards `http` | Refused with diagnosis, never a downgrade; session cookie stays `Secure` |
| Clock skew on challenge or session expiry | Server clock only; no client time trusted; document skew effect |
| Replay of a captured assertion or step-up | Refused; challenge single-use and bound to session |
| Step-up granted for action A reused for B | Refused; purpose-bound and one-shot |
| Two tabs, session revoked in one | Other tab shows signed-out state without data flash |
| Attacker hammers unlock or sign-in to lock the owner out | Throttle keyed so remote attempts do not penalise the loopback owner; throttling visible, with time remaining |
| Error messages for unknown secret vs denied vs wrong passphrase | Indistinguishable to a caller without authority; no timing difference worth exploiting |
| Session fixation, cookie scope, `SameSite`, `Secure` behind proxy | Tested with the real proxy path (`HUTCH_TRUSTED_PROXIES`) |
| WSL, headless Linux, remote desktop, no authenticator | Passphrase path works and is explained; no dead end |
| Device pairing code brute force | Bounded attempts, short life, tested |

## Vault lifecycle

| Case | Expected behavior |
|---|---|
| Forgot passphrase, has recovery key | Recovery works and forces a new passphrase and a new recovery key |
| Forgot both | Reset is explicit, shows what will be lost, requires step-up, audit survives or is stated not to |
| Recovery key shown once and not saved | Confirm step re-asks part of it before the vault becomes usable |
| Auto-lock while a run is in flight | Run fails with a typed explained error; no partial credential use; user sees why |
| Server restart | Vault locked; schedules and channel replies that need it show "needs vault", not silent failure |
| Database restored on another machine or without vault rows | Clear "vault missing/foreign" state; no crash; no overwrite of an existing vault |
| Crash during passphrase change, DEK rotation, export, migration | Atomic or resumable; proven by killing the process on a real database |
| Two server processes on one database | Single-writer behavior defined; second process cannot corrupt the wrap |
| Disk full, read-only filesystem, permission errors | Typed error, no half-written vault |
| scrypt parameters from a newer version | Refused cleanly with a message; bounds already enforced, keep tested |
| Swap, core dumps, tracebacks | Best-effort zeroing only; stated limit; no secret in exception text or `repr` |
| Many secrets (thousands), long names, Unicode names, huge values | Bounded sizes, clear errors, UI stays usable |
| Delete a secret that has grants, bindings, and audit rows | Cascades correctly; audit keeps the fact without the value |

## Agent access and egress

| Case | Expected behavior |
|---|---|
| Prompt injection asks the bot to reveal or send the key | Mediated path never returns it; reveal needs owner step-up and is not an agent action |
| Bot also has `shell` | Stated limitation; UI warns when a bot has both a reveal-capable grant and shell |
| Redirect to another origin, DNS rebinding, IPv6, IDN homograph, userinfo in URL, port confusion | Refused or canonicalised; tested against a real local server |
| Response echoes the credential encoded (base64, URL-encoded, split) | Documented limit; tests state exactly what is and is not caught |
| Huge or slow response, chunked, compressed bomb | Bounded, timed out, no memory blowup |
| Credential with newline, non-ASCII, or very long value | Refused before the request is built |
| Same secret granted to two bots | Independent grants, independent audit, revoking one leaves the other |
| Grant revoked mid-run | Next use refused; in-flight request outcome recorded |
| Approval-required grant in a scheduled (unattended) run | Waits or fails visibly; never auto-approves |
| Strict Offline | Vault network tool absent or refused, and the UI says why |
| Delegated or process-executed run | Fail closed with visible state unless a lease exists |

## Migration

| Case | Expected behavior |
|---|---|
| Existing install with plaintext keys | Copy, read-back verify, switch reader, then offer removal; never delete first |
| Ambient env key plus stored key | Both labelled; chosen one shown; env never silently wins |
| Partial migration then crash | Resumable; both copies valid until confirmed; no double billing path |
| Key in a file the owner also uses with another tool | Warn before removal; removal is opt-in and per item |
| Rollback | Decrypt back to the prior store on request, tested |

## Frontend

| Case | Expected behavior |
|---|---|
| Password manager autofill into unlock, create, change fields | Correct `autocomplete` (`new-password` vs `current-password`), no autofill of secret value fields, no `name`/`id` that triggers credit-card or username heuristics |
| Value in DOM, browser history, devtools, extensions, screenshots | No value until reveal; removed from DOM on hide and on navigation; `no-store`; reveal response not cached; masked by default |
| Clipboard | Copy clears after a stated delay where the platform allows; says when it cannot |
| Browser back and bfcache after lock | Locked state shown, no stale list of values |
| Screen reader, keyboard-only, reduced motion, high contrast, 200% zoom | All flows operable; dialogs trap and restore focus; live regions announce lock state |
| 360 px width | No horizontal overflow; destination origin shown in full, wrapped |
| Long origins, long secret names, RTL text | Truncation with accessible full text |
| Slow or failed API, double-click on destructive actions | Disabled while pending, idempotent, clear error |
| Light and dark themes | Contrast verified, including warning and danger states |
| Desktop (Tauri) webview | Same flows; passkeys behavior in the webview verified or documented as passphrase-only |

## Website and claims

| Case | Expected behavior |
|---|---|
| A claim slightly ahead of the code | Not published; claim list reviewed against `testing-and-validation.md` |
| Words like "unhackable", "military-grade", "zero-knowledge" | Banned unless literally true; "zero-knowledge" is not true here |
| Screenshots with real secrets or hostnames | Only generated canaries on a throwaway database |
| Limits hidden below the fold | Limits link sits next to each claim |

## Operations

| Case | Expected behavior |
|---|---|
| Audit table growth | Retention policy, export, stated behavior on prune |
| Incident: key leaked | Runbook: rotate at vendor, revoke grants, review audit, rotate DEK; one page, tested steps |
| `hutch doctor` | Reports vault state, remote sign-in misconfiguration, plaintext credentials remaining, ambient keys, without printing values |
| Logs | Redaction test over the full server log of a real session containing a canary |

