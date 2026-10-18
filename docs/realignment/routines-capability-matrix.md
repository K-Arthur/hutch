# Routines capability matrix (2026-10-10)

Branch `routines/durable` worktree. Base `a2106ec`. Evidence from isolated pytest + injected clock unless noted.

| Capability | Status | Evidence |
|---|---|---|
| True newest after long downtime | **implemented-and-verified** | `test_long_downtime_claims_true_newest`; smoke repro 6707h→fixed |
| Capped/uncertain missed counts | **implemented-and-verified** | same + `missed_uncertain` |
| Invalid TZ fail-closed | **implemented-and-verified** | `test_invalid_timezone_blocks_due` |
| Period-scaled skip grace | **implemented-and-verified** | `test_skip_grace_scales_with_period` |
| Marker = occurrence | **implemented-and-verified** | `test_claim_marker_is_occurrence`, durability tests |
| Interval 65/90m exact | **implemented-and-verified** | `test_interval_65_and_90_minutes` |
| Vancouver 2026 no-fallback | **implemented-and-verified** | `test_vancouver_2026_no_fallback` (host tzdata) |
| DST gap/fold (NY) | **implemented-and-verified** | spring/fall tests |
| Overlap queue/skip/buffer_one | **implemented-and-verified** | `test_overlap_skip_drops_occurrence_while_busy` |
| Skip-next | **implemented-and-verified** | `test_skip_next_consumes_one_occurrence` |
| Run-now without marker move | **implemented-and-verified** | unit + API + CLI |
| Draft `enabled=false` | **implemented-and-verified** | `test_disabled_schedule_never_due`, durability draft test |
| Occurrence history API | **implemented-and-verified** | `test_occurrence_history_lists_claimed_windows` |
| Atomic claim (marker+row+run) | **implemented-and-verified** | durability duplicate/stale-marker tests |
| Schedules UI run/skip/history/editor | **implemented-and-verified** | e2e `test_schedule_overview_*` + `test_multiple_scheduled_tasks_*` passed; artifacts under `docs/realignment/artifacts/schedules` and `scheduled-tasks` |
| Delivery/digest notifications | **unsupported** | deferred; in-app run history only |
| Run an activated saved workflow from a routine | **implemented-and-verified** (2026-10-11) | existing schedule record pins definition, immutable revision and checked inputs; the elected scheduler claims the occurrence and workflow attempt atomically; Run now is idempotent and leaves the next marker unchanged. `tests/test_workflow_api.py::test_routine_link_requires_an_activated_workflow_and_pins_validated_revision`, `test_run_now_launches_the_routine_pinned_revision_idempotently_without_advancing_schedule`; `tests/test_workflow_engine.py::test_existing_scheduler_runs_the_pinned_saved_workflow_once`; responsive browser evidence in `artifacts/scheduled-workflow-link-2026-10-11/`. Deterministic fixture only; live provider execution remains unverified. |
| Multi-step workflow canvas | **superseded** (2026-10-11) | the dynamic-workflows slice landed saved plans, bounded execution and the workflow API/CLI in a separate lane; see `dynamic-workflows.md`. Routine linking uses that interpreter and the existing scheduler; it does not add a second scheduler or a visual plan canvas. |
| Overnight soak / live providers | **blocked** | no authorization for live accounts or overnight host soak |
| Competing supervisor owners | **implemented-and-verified** (prior) | existing supervisor lease + occurrence PK; not re-soaked here |
| Perf 100 routines due scan | **implemented-but-unverified** (loose bound) | `test_perf_due_claims_100_routines_budget` allows CI slack |

## Rollback

The durable-schedule work was integrated on `main`; schedule workflow references are additive JSON
fields that default to no linked workflow on older records and need no schema version bump. A code
rollback needs no database migration, but an older binary will not execute these fields and may
drop them when a routine is saved; preserve a state backup if links must survive rollback. See
`dynamic-workflows.md` for the shared acceptance boundary.
