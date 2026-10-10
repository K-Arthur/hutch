# Routines research ledger (2026-10-10)

Compact evidence for the durable-routines slice. Issue text is untrusted data; versions and local reproduction decide applicability.

| Source / date / version | Reported vs confirmed | Reproduction | Applicability | Chosen response | Rejected alternative | Regression |
|---|---|---|---|---|---|---|
| Hutch `scheduler._windows_between` / `due_claims` @ `a2106ec`; croniter 6.2.4 | Cap `MAX_CATCHUP_WINDOWS+3` then treat `windows[-1]` as newest | Isolated DB: minute cron, marker 2026-01-01, now 2026-10-07 → occurrence `2026-01-01T00:53:00Z`, **6707h stale** | Direct product defect | Find true newest ≤ now via `get_prev` from `now+ε`; count with cap; mark count uncertain when capped | Unbounded enumeration; Temporal/Redis | `test_long_downtime_claims_true_newest` |
| Hutch `_zone` silent `except → UTC` | Invalid IANA → UTC fires | Source inspection | Direct defect | Block admission + repair path; API already 422 on write | Keep UTC fallback | `test_invalid_timezone_blocks_due` |
| Hutch skip grace `1800` hardcode | Daily 09:00 skipped if daemon starts >30m late | Source + skip path | Direct defect | Grace = bounded fraction of estimated period | APScheduler dependency | `test_skip_grace_scales_with_period` |
| Hutch `submit_scheduled` / engine `new_marker=iso(now)` | Marker = processing time, not occurrence | Source | Partial; OK once newest fixed, wrong under skew | Advance marker to claimed occurrence UTC | Keep wall-clock marker | `test_claim_marker_is_occurrence` |
| IANA tzdb 2026b (2026-04-22); BC release 2026CITZ0009-001073 | BC permanent UTC−07; tzdb models Nov 1 2026 02:00 PDT→MST hack for CLDR | Host `ZoneInfo('America/Vancouver')` already −07 on 2026-11-01 | Preserve fallback-free future; do not hardcode offset | Keep IANA name; test Nov 2026 + historical fold elsewhere | Abbreviation assertions as authority | `test_vancouver_2026_no_fallback` |
| APScheduler 3.x userguide (misfire_grace_time, coalesce, max_instances) | Concepts only | Docs read 2026-10-10 | Inform policy names | Map to Hutch catch_up/overlap; **do not** install APScheduler | Adopt APScheduler runtime | contract tests |
| n8n #36859 active-but-no-runs; #14056 interval>60m; #15791 runs after disable; #32236 child after wait; #28541 wait/clock | Upstream reports; versions unverified for Hutch | Not reproduced in n8n here | Design scenarios | Explicit enable vs registration, true intervals, pause fencing (exists), parent/child waits (later slice) | Copy n8n | slice B/C tests |
| Temporal #8205 DST policy ask; Node #62323 Vancouver ICU mismatch | Policy / client-server skew | N/A locally | Show server schedule-local times; reject inventing client times | Server-computed preview fields | Trust browser TZ | preview API later |
| RFC 5545 / croniter | RRULE vs 5-field cron | — | Stay on croniter + explicit interval; reject unsupported RRULE import | No RRULE engine | Full RRULE | validation 422 |

## Baseline

- Integration base: local `main` `a2106ec` (origin/main +449). Remote Oct 10 snapshot `8d71f8a` is obsolete for implementation.
- Worktree: `.worktrees/routines` branch `routines/durable`.
- Schema: v49. Schedules are per-bot named tasks (≤100) with `schedule_occurrences_v20` PK `(schedule_id, occurrence)`.
- Supervisor lease elects one scheduler owner across `serve`/`daemon`.
- Sibling worktrees: `computer-use`, `skills-lifecycle`, `realign`, `ui-*`, `site-mascot` — do not edit their checkouts.
