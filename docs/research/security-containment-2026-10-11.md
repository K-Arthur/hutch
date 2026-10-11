# Untrusted execution, injection containment, and scoped consent

Audit, integration, and adversarial evidence for three cooperating protections:
ephemeral containment of generated code, indirect prompt-injection containment
at the ingestion and effect boundaries, and consent bound to the exact executed
effect. This is the working record for the 2026-10-11 security slice.

Method: source audit first (no prior prompt was treated as proof), then
adversarial tests with real processes against owned sentinels, then fixes, then
re-verification on the integrated tree. Claims below name the code and the test
that proves them; anything not run is listed as unverified in §8.

## 1. Base, integration, and environment

* **Integration branch**: `security/containment` (worktree `.worktrees/security`),
  started from local `main` (`55f551b`), the declared integration branch — the
  stale `origin/main` (`8d71f8a`) was not used.
* **Merged lanes** (integrator resolutions recorded in the merge commits):
  `cost/guardrails` (budget bands + pause gate; migrations v51/v52),
  `grounding/evidence` (untrusted-ingestion evidence layer; migration renumbered
  to **v53**), `outputs/unified` (contained Python kernel, typed blocks,
  widgets, media, uploads; migration renumbered to **v54**).
  Excluded: `workflow/dynamic`, `mcp/s0-integration`, `synthesis/grounded`,
  `persona/adaptive` — all were actively being committed during integration.
* **Tests changed by renumbering**: `tests/test_outputs_store.py` now owns v54
  (`SCHEMA_VERSION >= 54`); schema pins follow the advancing-version convention.
* **Host** (verified, not assumed): Linux, bubblewrap **0.13.0**, systemd-run and
  prlimit present, unprivileged user namespaces enabled, uid 1000.
  `hutch.sandbox.status()` probe passes with backend
  `bubblewrap+systemd-user-scope`.
* **Integrated-tree suite before this slice**: `pytest tests --ignore=tests/e2e`
  → **2383 passed, 9 skipped** (10:59, disk-backed basetemp; an earlier run under
  a full `/tmp` tmpfs was correctly discarded as corrupted by ENOSPC).
* **Browser**: Playwright 1.63 / Chromium from `~/.cache/ms-playwright`.
* **Measured on this host** (10 warm calls after one cold start, contained kernel):
  cold start including first execution **0.40 s** (budget ≤ 2.5 s), warm
  round-trip p50 **1.3 ms** / p95 **1.9 ms** (budget ≤ 300 ms), manager close
  **≈1 ms** (the kernel process is owned by `--die-with-parent` and the session
  tree teardown is verified in `tests/test_native_containment.py`). These are
  local reference-machine numbers, not cross-device claims.

## 2. Trust domains and data flow

```
 untrusted text/media ──► ingestion tools (web_fetch, live_search, inspect_media,
 (web, feeds, files,       documents, uploads)  ── record provenance/source rows
  PDFs, CSV cells,         │
  tool results, MCP)       ▼
                    ContentEnvelope facts             trusted plane
                    (schemas, quotas, spans)          ─ system prompt, policy,
                           │                            approvals, receipts
                           ▼
                    model planner (may be injected) ──► tool call proposal
                           │                                  │
                           ▼                                  ▼
                    context composer ──────► dispatch ──► POLICY + APPROVAL GATE
                    (bounded, role-typed)         (schema, identity, hashes, quotas)
                                                          │
                              ┌───────────────────────────┼────────────────────┐
                              ▼                           ▼                    ▼
                     code executor (bwrap)        file/broker boundary   connector broker
                     workspace-only, no net       path jail, receipts    account-scoped,
                     fail-closed                  effect intents         reauthorized per op
                              │                           │                    │
                              └──────────► artifact registry ◄─────────────────┘
                                           (hashes, versions, promotion)
```

The model is treated as **potentially influenced by hostile input at all
times**: the planner is in the untrusted tail of the diagram. Enforcement is at
the executor/broker boundaries, so the outcome is identical whether the plan
came from a cooperative operator or an injected page (proved by
`tests/test_hostile_planner_enforcement.py`, which never involves a model).

## 3. Assets the boundaries must protect

Credentials and connection keys (state dir), other conversations and
workspaces, the store database and control plane (approval endpoints, grants,
receipts), account integrations (Google/Outlook/ChatGPT), provider budgets,
host processes/devices, and the public posting identity. Sentinels used in
tests are synthetic; no real credential, account, or third-party service was
touched.

## 4. Enforcement inventory (audited on the integrated tree)

| Control | Enforced where | Regression evidence | Status |
|---|---|---|---|
| Generated Python runs only in bwrap strict; no uncontained fallback | `workspace/manager.py:k​ernel_argv/_contained_spawn` (refuses `HUTCH_SANDBOX=off`, fails closed when the probe fails) | `tests/test_native_containment.py`, `tests/test_workspace_manager.py`, `tests/test_tools_python_exec.py` | verified (real processes, this host) |
| Executor cannot read host sentinels / other conversations / state dir / DB | bwrap ro-bind layout: only `/usr`, interpreter+venv+src ro, workspace rw | `test_native_containment.py::test_host_credential_and_state_sentinels_are_unreadable`, `::test_another_conversations_workspace_is_invisible` | verified |
| No IPv4/IPv6/DNS/Unix-socket egress from the executor | `--unshare-all`, private `/tmp`,`/run` | `::test_no_ipv4_ipv6_dns_or_host_unix_socket` (owned listeners, never connected) | verified |
| Writes confined to workspace; private `/tmp`; ro system tree | bwrap binds | `::test_writes_are_confined_to_the_workspace` | verified |
| PID namespace; detached descendants die with the session | `--unshare-pid`, `--die-with-parent`, process-group teardown | `::test_pid_namespace_sees_only_the_sandbox`, `::test_a_detached_descendant_dies_with_the_session`, `tests/test_sandbox.py` (shell path) | verified |
| CPU/mem/procs/files/wall/output caps | systemd-run scope + prlimit + kernel budgets | `test_native_containment.py::test_effective_backend_identity...`, `tests/test_workspace_bounds.py` | verified |
| Hard denials (secrets, exfil, sudo, pipe-to-interpreter, workspace escape) before approval/sticky | `safety.py:PolicyEngine` | `tests/test_safety.py`, `tests/test_hostile_planner_enforcement.py` | verified |
| Exact-effect consent: approval frozen over arguments, fingerprint-bound, atomic single resolution | `approvals.py`, `action_receipts.py:freeze`, `store.decide_approval(expected_hash=…)` | `tests/test_approval_cas.py`, `tests/test_file_approval.py`, `test_tools_python_exec.py::test_a_decision_shown_different_code_cannot_approve_this_cell` | verified |
| Outward actions always ask; sticky never applies | `approvals.py` SR-4 rule; `safety.py:_OUTWARD_PROGRAMS` | approval/file/safety suites | verified |
| Effect intents + sealed receipts; no silent replay | `action_receipts.py` triggers; `begin_effect` | `tests/test_receipts.py`, `tests/test_action_intents.py` | verified |
| Egress guard: address-based screening, every answer public, DNS pinning, redirect re-checks, bounded body | `netguard.py:safe_get` | `tests/test_netguard.py` (rebinding, redirects, multi-answer, bounds) | verified |
| Browser egress pinned independently of route checks | `browser_proxy.py` | `tests/test_browser_proxy.py` (CONNECT pinning, rebinding answer, WS upgrade) | verified |
| Strict Offline worker: credential-free mounts, network/PID isolation, Unix-socket broker | `sandbox.py:offline_worker_argv`, `offline.py` | `tests/test_offline_mode.py` (now runs end-to-end on this host after the probe fix: 55 passed with sandbox tests, no skips) | verified |
| Untrusted payload cannot forge envelope framing or contract notes | `runtime/builtin.py:_neutralize_structural_markers` (fix in this slice) | `tests/test_runtime_builtin.py::test_a_tool_result_cannot_close_or_forge_its_own_envelope` | verified |
| Untrusted web content is assessed, disclosed, never rewritten | `ingest.py`, `tools/webfetch.py` (fix in this slice) | `tests/test_ingest_assessment.py` | verified |
| HTML comments removed from visible text, assessed separately, count disclosed | `ingest.py:strip_html_comments`, `webfetch.py` | `test_ingest_assessment.py` | verified |
| SVG media rejects scripts/handlers/external refs **and CSS url()/@import fetches** | `media/validate.py:sanitize_svg` (CSS gap fixed in this slice) | `tests/test_media_validate.py` | verified |
| Widgets render schema-validated blocks with a text fallback; no untrusted script execution path in the SPA | `outputblocks.py` validation, `widgets.js` (escapes + defense-in-depth SVG scrub), `index.html` (no inline scripts) | `tests/test_outputblocks.py`, `tests/test_widgets_static.py`, browser journeys | verified |
| Strict CSP on the **local** surface (default-src/script-src/connect-src 'self', frame-ancestors none) | `server/security.py` (fix in this slice) | `tests/test_api.py::test_the_local_surface_carries_the_strict_csp_too`, `tests/test_remote_pairing.py` | verified |
| Origin/Sec-Fetch-Site CSRF checks, loopback Host check | `server/security.py` | `tests/test_service.py`, `test_remote_pairing.py` | verified |
| Model-facing tool results travel by provider-native role in native mode; bounded data framing otherwise | `runtime/builtin.py:append_tool_result` | `tests/test_runtime_builtin.py` | verified |

## 5. Defects found and fixed in this slice

1. **Envelope breakout in the prompt/constrained protocol** (`runtime/builtin.py`).
   Tool output was interpolated into `<tool_result …>…</tool_result>` with no
   escaping, so a returned page containing `</tool_result>`, a second opening
   tag, or a `[tool-contract]` line could forge the framing and impersonate a
   contract note. Fix: escape only the delimiter *spelling* (`&lt;…`, `&#91;…&#93;`),
   keeping every payload byte readable. Regression:
   `test_a_tool_result_cannot_close_or_forge_its_own_envelope` proves exactly
   one genuine envelope exists and the payload remains visible.
2. **CSS-based beacons in stored SVGs** (`media/validate.py`). The sanitizer
   rejected `<script>`, `on*`, and external href/src URLs, but not
   `url(http…)/@import` inside `<style>` or `style=` — an external fetch when an
   animation is inlined. Fix: reject external CSS URL references, keep internal
   `url(#fragment)` and plain CSS working (positive test included).
3. **Strict CSP not applied to the local dashboard** (`server/security.py`).
   The policy existed only for remote/paired sessions. Fix: send it for every
   response; the one inline `onclick` in the SPA error state became a delegated
   listener so the policy is actually enforceable. Browser journeys
   (dashboard polish, inline approval, stale-approval race) pass under it.
4. **Strict Offline falsely reported unavailable when Hutch ran from its venv**
   (`sandbox.py:_probe_offline_egress`). The egress probe mounts only the system
   tree but resolved `python3` through PATH — the venv shim — whose target is
   not mounted, so the probe failed for an interpreter-path reason and every
   Strict Offline route degraded (and its end-to-end test skipped) on such
   hosts. The probe now chooses an interpreter under `/usr` and reports honestly
   when none exists. Related hardening: `OfflineBrokerSet` and the probe no
   longer hardcode `/tmp` for host-side broker directories (they honor
   `TMPDIR`), so a full tmpfs cannot masquerade as an isolation failure.
   Effect verified on this host: `tests/test_offline_mode.py` now runs the
   network-isolated worker end-to-end and the file is fully green (55 passed,
   no skips with `tests/test_sandbox.py`).

Also recorded as corroborating audit results (no change needed): the workspace
kernel's approval detail already carries the exact source and the approval hash
covers it; `safe_get` pins DNS; `browser_proxy` pins CONNECT/WebSocket
independently of route interception.

## 6. Research mapping

| Ref | What it is | Applicability / design response | Test |
|---|---|---|---|
| R1 OWASP LLM prompt-injection cheatsheet | Layered controls guidance | Adopted as layering: ingestion assessment + typed roles + effect-time authorization; no single control claimed complete | this doc §4 |
| R2 NCSC data/instruction separation | Separation limits | System/contract text states tool results are data; delimiter escaping; enforcement does not depend on the model obeying | `test_a_tool_result_cannot_close_or_forge_its_own_envelope`, hostile-planner suite |
| R3 gVisor security boundaries | Narrower host-kernel interface | Evaluated, **not adopted**: bwrap+PID/network namespaces+prlimit+systemd scope meets the tested threat model on this host; gVisor noted as the upgrade path for untrusted *multi-tenant* code | n/a (decision, §8) |
| R4 Docker/rootless mechanics | Container isolation semantics | Not adopted (no requirement to run a daemon; rootless container ≠ microVM); recorded comparison in §8 | n/a |
| R5/R6 Pyodide embedding + worker; postMessage validation | Browser Wasm/JS bridge risks | **Not applicable as shipped**: no Pyodide/WASM anywhere (`grep` clean). Widgets are trusted components over schema-validated data; decision recorded so a future Wasm path must implement the restricted-embedding checklist | `tests/test_widgets_static.py` |
| R7 OpenCode permission-vs-sandbox statement | Prompt-level permissions ≠ OS containment | Hutch's model: policy for usability, bwrap for containment; `run_python` refuses uncontained execution even when permission says allow | `test_native_containment.py`, `test_tools_python_exec.py` |
| R8 CaMeL control/data-flow research | Capability inspiration | Adopted as inspiration only: no complete information-flow tracker is claimed; grants/capability snapshots + broker-side authorization are what is enforced | hostile-planner suite |
| R9 AgentDojo-style evaluation | Utility/attack methodology | Adopted partially: matched benign+adversarial fixtures here; full held-out model-driven benchmark **not run** (no budget authorization) | §8 |
| R10 ARIA modal pattern | Approval drawer accessibility | Existing drawer implemented previously; verified keyboard/focus journeys remain green | `test_browser.py` approval journeys |
| R11 Playwright traces | UI evidence | Used for browser verification (trace/captures in `docs/realignment/artifacts/`) | §7 |
| F1 n8n Pyodide advisory | Node-hosted Pyodide escapes | Not applicable as shipped (no Pyodide); recorded as a prerequisite constraint for any future notebook/Wasm feature | n/a |
| F2 Grist Pyodide-on-Node advisory | Configuration-specific sandbox failure | Same as F1 | n/a |
| F3 OpenCode web-UI XSS/local execution | Hostile page reaching a local control surface | Local surface now carries the strict CSP; Origin/Sec-Fetch-Site checks already present; media/uploads served verified+attachment/sanitized | `test_api.py` CSP test, `test_remote_pairing.py` |
| F4 approval-fatigue report | Humans bypass noisy approvals | Narrow sticky grants for scoped benign work; outward actions always ask; consent bound to exact effect so "always" cannot silently widen | `test_tools_python_exec.py`, approval suites |

## 7. Adversarial acceptance results (mission §12)

| Scenario | Result on this tree |
|---|---|
| Useful analysis under attack | Enforceable today with contained `run_python`, uploads, documents and typed blocks; the end-to-end browser journey for widgets/approvals is green. A single scripted "thread+PDF+CSV" model-driven showcase was **not** added (would require a hosted model call); its parts are covered by `test_ingest_assessment.py`, `test_native_containment.py`, and `test_hostile_planner_enforcement.py` |
| Model ignores the boundary | `test_hostile_planner_enforcement.py`: secret reads, exfiltration, pipe-to-interpreter, workspace escape, unknown tools, malformed args, fail-closed Python — all denied with zero effects, without any model in the loop. Live-model susceptibility **not measured** (§8) |
| Browser/Node distinction | No Pyodide/Node execution path exists in the product; the browser executes only first-party JS. Decision + conditions for a future path recorded (§6) |
| Native containment | §4 rows 1–6, real bwrap processes, exact allowed/denied effects, backend identity asserted |
| Malicious rich content | SVG sanitizer (server) + client scrub + strict CSP + text fallbacks; forged envelope framing escaped; `test_media_validate.py`, widget suites, browser journeys |
| Content preservation | `test_ingest_assessment.py`: quoted attack phrases, tutorials, multilingual imperatives, figures/negations stay byte-identical; findings only annotate |
| Multimodal/persistent injection | Vision frames travel as explicit bounded attachments with "describe only what is visible" guidance and exact transmission recording (`runtime/builtin.py`); OCR is not used as a sanitizer. **Not tested**: instructions embedded in an image reaching a vision model (requires a vision-capable route) |
| Consent races | Wrong-hash approval cannot decide (`test_tools_python_exec.py`); stale two-device click (`test_browser.py`); duplicate/lost-response key tests exist from prior lanes |
| Egress coverage | `test_netguard.py` + `test_browser_proxy.py` + `test_native_containment.py` (owned listeners, DNS pinning, redirects, IPv4/IPv6, Unix socket) |
| Permission fatigue | Scoped sticky grants for repeated Python/shell work; outward still asks; exact-effect fingerprints prevent silent widening |
| Cancellation and exhaustion | Workspace bound/interrupt/lost suites + kernel detached-descendant teardown; budget bands (merged `cost/guardrails`) add warn/pause/Ceiling admission |
| Partial external result | Pre-existing action-receipt/reconciliation machinery (`action_receipts.py`, send suites) — unchanged, audited |
| Full product journey | Browser: dashboard polish + both approval journeys pass under CSP. The failing `test_tool_permissions_are_clear_and_save…` journey is **pre-existing at the base** (listed in the base verification's failed-node set), not introduced here |

## 8. Residual risks and unverified surfaces (honest list)

* **Envelope mode is heuristic context, not an execution boundary.** The
  escaping closes framing forgery, not instruction susceptibility. Enforcement
  remains broker-side.
* **Vision-model injection** (instructions inside images) was not exercised: no
  vision-capable route/model was run. The pipeline records what was transmitted;
  the content stays untrusted; but instruction susceptibility of a vision model
  is unmeasured here.
* **Live-model susceptibility** (does a real model obey a hostile page) was not
  measured — no paid model calls were authorized. Deterministic fixtures test
  enforcement, not model behavior.
* **`live_search`/`inspect_media` output is not yet run through `ingest.assess`**
  (only `web_fetch` is wired). The evidence layer already stores provenance; the
  annotation is a follow-up for the grounding lane to adopt.
* **No Wasm/Pyodide path exists**, so [F1]/[F2] are not applicable today; any
  future rich-notebook path must satisfy the restricted-embedding checklist
  before shipping.
* **gVisor/OCI backends were not adopted or benchmarked** on this host; bwrap
  is not a hardened VM (kernel-namespace escapes are out of scope, as stated in
  `sandbox.py`).
* **`HUTCH_SANDBOX=off` remains a documented global switch for the shell tool.**
  `run_python` refuses it by construction; a bot that turns containment off can
  still run shell commands uncontained — a deliberate, visible legacy mode, not
  an untrusted-code fallback. Migration guidance lives in `docs/safety.md`.
* **Pre-existing browser failures** at the integration base are not fixed here
  (tool-permissions journey among them); they predate this slice and were
  reproduced independently.
* **Host disk pressure**: `/tmp` (12 GiB tmpfs) was full during an early run,
  corrupting it; results were discarded and rerun with disk-backed basetemps.
  Test commands must use `TMPDIR`/`--basetemp` outside `/tmp` on this host.

## 9. Reproduce

```bash
cd .worktrees/security
uv sync --extra dev --extra browser --extra jetstream
TMPDIR=/var/tmp/hutch-security-tmp uv run pytest tests --ignore=tests/e2e \
  --basetemp=/var/tmp/hutch-security-pt/final -p no:cacheprovider     # full non-e2e
TMPDIR=/var/tmp/hutch-security-tmp uv run pytest tests/test_native_containment.py \
  tests/test_hostile_planner_enforcement.py tests/test_ingest_assessment.py \
  tests/test_media_validate.py tests/test_runtime_builtin.py -q       # this slice
PLAYWRIGHT_BROWSERS_PATH=/home/kevina/.cache/ms-playwright TMPDIR=/var/tmp/hutch-security-tmp \
  uv run pytest tests/e2e/test_browser.py::test_dashboard_polish_keeps_work_feedback_steady_and_headings_readable \
  "tests/e2e/test_browser.py::test_inline_chat_approval_is_one_click_and_preserves_conversation" -q
```
