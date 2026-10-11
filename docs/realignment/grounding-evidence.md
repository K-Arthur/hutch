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
| Jetstream README (read 2026-10-11) | Cursors are **instance-local seqs** (inclusive, monotonic, non-contiguous, at-least-once), v1 timestamp cursors accepted on the same parameter and split by magnitude (>=1e15 = unix-µs); `CursorTooOld` when below floor; witnessed_at is the only correct resume unit | **Live-verified same day**: `wss://jetstream.us-west.bsky.network` reachable (HTTP 200; protocol-correct handshake); 227 events scanned in an 8 s window; cursor resumed to a later window. The live read also exposed a v2 wire shape (frames nested under `payload`, ISO `time`/`witnessedAt`) the v1-shaped parser silently ignored | `grounding/streams.py` parses both wire shapes, **never compares cursor namespaces**, dedupes by seq, advances the read position even when the term filter matches nothing (a continuity bug the live resume check caught), rewinds explicitly on instance switch, and maps `CursorTooOld` to a bounded gap state |
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

## Frontend design research and route approval (2026-10-11)

The user approved a route for the evidence panel before implementation (question tool, answer:
"Run panel + chat entry"). Research actually inspected, with live interfaces captured in a real
headless Chromium in this environment and read as images:

| Inspected | URL | Pattern that transferred |
|---|---|---|
| Full Fact fact-check article | https://fullfact.org/conflict/video-compilation-us-strikes-iran-old-footage-and-fake/ | "What was claimed / Our verdict" split; the finding is a scoped sentence; metadata rail; attributed check |
| Ground News home | https://ground.news/ | Explicit sample denominators plus a distribution bar; a blindspot badge rather than a truth score |
| Google Fact Check Explorer | https://toolbox.google.com/factcheck/explorer | Claim-level rows with *attributed* ratings, publisher and age |
| Wikipedia revision history | https://en.wikipedia.org/w/index.php?title=Black_Sea&action=history | Corrections as new rows with summaries and diffs; nothing rewritten |

Not inspected, disclosed: Figma Community pages and their CDN previews were unreachable from this
network through three routes (direct fetch, headless Chromium, a public reader proxy — CloudFront
block on every one). The Mobbin connector answers "requires a paid plan". No Figma Community frame is
claimed as inspected; the Motif plugin's text description informed wording only.

Patterns deliberately not transferred: partisan lean axes, universal real/fake badges, single truth
scores. Routes offered: run panel + chat entry (chosen), drawer-only, sources-first timeline,
receipts strip. The chosen panel keeps the existing dark token set and Archivo display face.

## Verification record (2026-10-11)

- Offline tests: `tests/test_grounding_*.py` — temporal (13), dedup (7), acquire (14), streams (11),
  media (6), tools/runtime delivery (12), API (4), adversarial scenarios (5); plus 2 real-browser
  regression tests in `tests/e2e/test_grounding_panel.py` (1440 and 360 CSS px).
- Live read-only checks (`HUTCH_LIVE_TEST=1`): BBC feed retained 5 items with declared dates;
  HN retained 5 stories; Wikimedia stream read 40 events with a structured cursor; Jetstream read
  227 events in an 8 s window and resumed from the stored seq cursor to a later window (advanced
  even though that window matched nothing); GDELT returned HTTP 200 earlier in the day and
  `rate_limited` during the later run (reported honestly).
- Browser validation of the panel (seeded fixture, real server, headless Chromium): panel, scoped
  label, 2 source rows with text independence chips, 6 outcome rows, 1 loaded frame served from the
  hash-verified API, revision list, chat entry link; zero console errors; no horizontal overflow at
  1440 / 900 / 360. Screenshots: `docs/realignment/artifacts/grounding/panel2-{desktop,tablet,phone}.png`.
- Integration base: `main` (4ac6041) + `toolcall/unified` (clean merge) + `wcag22-audit-fixes`
  (29 conflicts: 26 regenerated artifacts resolved to main's captures, 4 code/doc files resolved by
  keeping both sides). Focused suites on the merged tree pass. `main` then advanced independently
  (Agent Skills, toolcalling and documents merges at `55f551b`); the grounding branch merged that
  head as `4e217ba` (2 real conflicts — CHANGELOG and the tool registry — resolved by union;
  regenerated artifacts taken from the grounding side). Final full offline suite on the combined
  tree: **2021 passed, 5 skipped, 1 failed** — only
  `test_code_handoff.py::test_interactive_process_keeps_terminal_and_owns_a_separate_group`, a
  load-sensitive TTY race that passes 3/3 in isolation and also failed on the pre-grounding
  merged tree. `test_docgen_docx.py::test_identical_specs_produce_identical_bytes` exposed a real
  determinism defect (python-docx stamps ZIP entries with the local clock), now repaired in
  `docgen/zippack.py` and verified byte-identical across a 2.2 s boundary and across the whole
  documents suite (125 passed).
- Integration repairs made on the merged tree: v51 tables taught to the delegation
  schema-downgrade helper; the documents schema pin updated; the sandbox home-containment test
  strengthened to assert real home entries are invisible rather than counting an environment
  dependent error string.

## Classification of each source/model/workflow

| Item | Class |
|---|---|
| RSS/Atom feeds, Hacker News, Wikimedia EventStreams | **Verified live** (read-only) |
| GDELT DOC 2.0 | **Verified live earlier; 429 under repeated use → honest `rate_limited`** |
| Bluesky public search | **Blocked from this network (HTTP 403)** — implemented, unverified live |
| SearXNG | **Implemented; fixture-verified** — needs the operator's instance |
| Jetstream websocket | **Verified live 2026-10-11** (bounded windows; `seq` cursors persisted and resumed; `CursorTooOld` gap state tested against a local instance) |
| Image/video input to models | **Implemented and wire-verified** (OpenAI-compatible, Anthropic, Ollama conversions); a live hosted vision call was not made and is not claimed |
| C2PA validation | **Presence verified against fabricated markers; signature validation unsupported without a maintained verifier** |
| Reverse-image / image fact-check | **Unsupported by design** (egress permission not held) |

## Remaining gaps

- No live hosted-model run was performed end-to-end (no provider call was made with media), so
  "frames reached a real hosted model" remains implemented-and-wire-tested, not live-verified.
- The Bluesky public *search* lane stays `blocked` from this network; the Jetstream `stream`
  lane is live-verified and needs the optional `hutch[jetstream]` extra.
- SearXNG awaits a local instance.
- Phone-width panel was inspected at 360 px; physical-device and screen-reader passes were not run.
- Budgets are defaults asserted in code, not tuned against large real corpora.
