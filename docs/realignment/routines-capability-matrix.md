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
| Multi-step workflow canvas | **unsupported** | out of smallest architecture |
| Overnight soak / live providers | **blocked** | no authorization for live accounts or overnight host soak |
| Competing supervisor owners | **implemented-and-verified** (prior) | existing supervisor lease + occurrence PK; not re-soaked here |
| Perf 100 routines due scan | **implemented-but-unverified** (loose bound) | `test_perf_due_claims_100_routines_budget` allows CI slack |

## Rollback

Revert `routines/durable` commits. Additive Schedule JSON fields default safely on older docs; no schema version bump required for this slice.
