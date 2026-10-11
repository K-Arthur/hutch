# Grounding slice: plan, research ledger, and evidence record

Status: integration + implementation in progress on branch `grounding/evidence`
(worktree `.worktrees/grounding`). Integration base decision below. No push, no deploy.

## Integration base decision (2026-10-10/11)

Inspected topology (read-only, `git`):

| Ref | State |
|---|---|
| `origin/main` | `8d71f8a` (the inspected remote main) |
| local `main` | `4ac6041` — documents pipeline (schema v50), routines/durable, earlier WCAG merge; **lacks** the Agent Skills work and the tool-transpiler work |
| `wcag22-audit-fixes` | `2872f4f` — agent-skills lifecycle (17 commits) + WCAG work; **lacks** documents and tool-transpiler |
| `toolcall/unified` | `b54d01f` — compiled tool-calling contract (`src/hutch/toolcalling/`, provider/runtime changes); based near main's tip |
| `realign/platform` | `4af8002` — fully contained in main (no unmerged work) |
| `routines/durable` | `c869a5a` — fully contained in main |
| other worktrees | site/expressive-mascot, ui-run-wait, ui/redesign, outputs, computer-use, skills-lifecycle — no unmerged code beyond the above |

Decision: the correct integration base is **main + toolcall/unified + wcag22-audit-fixes**. `toolcall/unified`
merges into main cleanly (verified with `git merge-tree`, 0 conflicts). `wcag22-audit-fixes` produced 29
conflicts: 26 regenerated evidence artifacts (resolved by keeping main's regenerated captures), plus
`CHANGELOG.md`, `src/hutch/models.py`, `src/hutch/tools/__init__.py`, `src/hutch/cli.py` — resolved by
keeping **both** sides (documents+routines+tool-protocol from main; skills bindings from wcag). The merged
tree is committed on `grounding/evidence`; the source branches are untouched. No obsolete master-only
restriction was imposed.

## Research ledger (source / date / reported / confirmed here / response)

| Source (date) | Reported | Confirmed locally | Response in Hutch |
|---|---|---|---|
| SearXNG #3358 (2024-03; fixed via PR #5793, 2026-03) | Bing `time_range` returned out-of-range results; quotes made it worse | Not reproduced (no SearXNG instance); defect class accepted | `grounding/acquire.py` **always validates date bounds locally** and counts `dropped_out_of_range` per attempt; a time-filtered zero-result is never reported as "nothing happened" |
| SearXNG #3400 (2024-04; closed as by-design) | With a date filter, news engines that do not support it are **disabled**, so "no results" | Same class confirmed by reading thread + docs; no instance to reproduce | Adapter records `unresponsive_engines`/disabled engines and the fallback retry-without-filter + local date validation; outcome states distinguish `zero_results` / `disabled` / `unavailable` |
| Jetstream README (read 2026-10-11) | Cursors are **instance-local seqs** (inclusive, monotonic, non-contiguous, at-least-once), v1 timestamp cursors accepted on the same parameter and split by magnitude (>=1e15 = unix-µs); `CursorTooOld` when below floor; witnessed_at is the only correct resume unit | Read from upstream README at purity; live websocket blocked from this network (no `websockets` dep installed; public host not probed) | `grounding/streams.py` **parses cursor kind by namespace, never compares across kinds**, dedupes by seq, keeps a rewind margin on instance switch, and maps `CursorTooOld` to a bounded gap state. Jetstream adapter reports `unsupported` (dependency) / `blocked` (host) instead of faking a connection |
| Jetstream issue #349 (2026-09; fixed v0.2.3) | A v1 timestamp cursor fed into v2 seq dedup silently drops **all** events; no error, just quiet | Root cause read from issue; regression test reproduces the mixed-namespace comparison in our parser | Test `test_cursor_namespace_mismatch_never_silently_drops`: v2 client must reject/migrate mixed cursor kinds explicitly |
| Gemini video understanding docs (updated 2026-10-09) | Static mode samples **1 fps**; rapid motion can be missed; audio processed; MM:SS references; >20MB needs Files API; prompt after media | Read from current docs | `grounding/media.py` samples frames at claim-relevant + boundary times, records exact inspected frame times and explicitly reports uninspected intervals/audio; frames (not "the video") are what reach the model through the tool contract |
| Wikimedia EventStreams docs (page rev 2026-08-20) | SSE `id` is a JSON array of topic/partition/(offset\|timestamp); `Last-Event-ID` resume; **timestamps are the multi-DC-stable resume unit, offsets are per-cluster**; canary events ≤1/hour signal broken-vs-quiet; 15-min server connection cap; 7–31 day history; no server-side filtering | **Confirmed live** on 2026-10-11: 946 events in 8s, `id` arrays observed with `{topic,partition,timestamp}` and `{topic,partition,offset:-1}` | Verified live stream adapter: verbatim `Last-Event-ID` resume, canary-aware liveness, client-side filtering, bounded reconnect backoff, cursor stored as structured JSON with schema version |
| C2PA 2.2 Explainer (read 2026-10-11) | Content Credentials are tamper-evident provenance, **not truth verdicts**; absence is normal; removal possible; signer trust is a separate axis | Read from spec site; no `c2pa` verifier installed locally | `media.py` records C2PA states `absent / present_unverified / verified / invalid / unsupported`; never renders a truth badge; never hand-rolls crypto |
| Google Fact Check `imageSearch` (noted) | Requires a **public image URL**; sending private media to public services is separate egress | Not called (no key, and egress rule) | No reverse-image adapter ships enabled; the contract exists as an honest `unsupported` check, never an implicit upload |

Additional live probes (2026-10-11, read-only): GDELT DOC API works (HTTP 200, `seendate` observed);
Bluesky `public.api.bsky.app` returns 403 from this network (adapter implemented, marked blocked);
Mastodon public timeline requires auth now (422) — not shipped; HN Algolia works; BBC/Verge/Axios/HN RSS
feeds work; Wikimedia SSE works. `ffmpeg`/`ffprobe`, Pillow 12.3 available in the venv.

## Contracts (frozen before implementation)

- **Time roles are never merged.** occurrence/validity, announcement, publication, source modification,
  upload/capture, index/stream observation, retrieval, verification. Stored as `TimestampValue`
  (raw text + parsed instant/interval + precision + tz + method + uncertainty). Unknown tz is not UTC;
  date-only is a civil-day interval; GDELT `seendate` is an index-observation timestamp, not the
  publisher's own date; run/transcript timestamps are never evidence of when an external event happened.
- **One clock.** `grounding.clock.Clock` is injected into tools, parsers, tests, and rendering:
  UTC instants for ordering, IANA zones for civil intent, monotonic for durations. Tests freeze the clock.
- **Evidence is bound to claims.** relations `supports|contradicts|context|reports_allegation`, independence
  `independent|same_origin|syndicated|unknown`. "An account posted X" and "X occurred" are separate claims.
  Ten copies of one claim are spread, not corroboration; origin clusters are computed from content and
  syndication structure, not popularity.
- **Acquisition outcomes are distinct:** `ok / zero_results / partial / disabled / unavailable / blocked /
  timeout / error`, each with freshness (`snapshot|polled|stream`) and dropped-result counters.
- **Media observations are separate from verdicts.** File provenance, perceptual observation, context
  match, and claim support are separate records. Inspected frame times and missing intervals are recorded;
  "no manipulation established" is not "authentic".
- **Budgets before optimization:** per investigation — ≤6 adapters, ≤4 concurrent fetches, ≤25 s per
  adapter, ≤40 sources retained, ≤90 s wall for a search, ≤6 frames per video, ≤8 MB image / 40 MB video,
  1200 s investigation wall; GDELT ≥5 s between requests (host gate); stream: ≤600 events or ≤120 s per
  bounded read, ≤15 min between reconnects.
- **Threat model:** all acquired text/metadata/captions are untrusted evidence; URLs go through
  `netguard` (SSRF, redirect, DNS re-checks); media parsing is bounded and out-of-process where possible
  (ffprobe/ffmpeg); no active content is ever served from Hutch's origin; no credentials in URLs or
  reports; private investigation data never leaves the machine except where the operator's configured
  model route already receives the run context (with the existing per-route approval), and camera/media
  egress to reverse-search services is a separate, unimplemented permission.

## Implementation order

1. `grounding/{clock,temporal}.py` + tests (time roles, parsing, as-of).
2. `grounding/{dedup,evidence}.py` + store migration v51 + tests (clusters, independence).
3. `grounding/acquire.py` + `streams.py` + tests (fixtures for the four failure scenarios; live smoke
   marked `HUTCH_LIVE_TEST`).
4. `grounding/media.py` + tests (fabricated benign assets, ffmpeg sampling, C2PA presence).
5. Tools (`live_search`, `inspect_media`, upgraded `web_fetch`), runtime image attachment, provider wiring.
6. `/api/v1` evidence resources + UI panel (design gate: research + approved route before UI code).
7. Adversarial scenarios, docs, budgets/rollback, continuation ledger entries.

## Rollback

Everything is additive: a new schema migration (v51) adds tables only; new tools are opt-in per Bot;
`web_fetch` keeps its old fields and adds a metadata block; no existing route behavior changes except
new optional fields. Reverting the branch restores the pre-slice behavior; the schema upgrade is
additive and the migration backup (`.db.bak-v50`) is kept by the existing upgrade path.
