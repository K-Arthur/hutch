# Grounding: live evidence, time, and media checks

Hutch can ground an answer in live sources without pretending a plausible search result is
proof. This page documents the shipped behavior, how to configure it, what is verified on a
real network, and what remains unverified.

The implementation lives in `src/hutch/grounding/` (clock, temporal, dedup, acquire,
streams, media, report), the store tables added by schema v53, the `live_search` and
`inspect_media` tools, the upgraded `web_fetch`, and the Evidence panel in run detail.

## What it does

- **Fan-out search (`live_search`)** — bounded parallel retrieval across complementary
  lanes; every adapter reports a distinct outcome (`ok`, `zero_results`, `partial`,
  `disabled`, `unavailable`, `blocked`, `rate_limited`, `timeout`, `error`) with dropped
  out-of-range counts. Partial results ship with a missing-source ledger; "no new evidence
  found in these sources" is never reported as "nothing happened".
- **Time, honestly** — every timestamp keeps its role (occurrence, announcement,
  publication, modification, capture, upload, index/stream observation, retrieval,
  verification), raw text, precision and zone. Unknown time is not UTC and not "now";
  relative phrases ("ten minutes ago") anchor to their own document or request, never to
  the reader. Date-only values are civil-day intervals. Two historical modes stay apart:
  *what evidence was available by T* versus *what we now know about events before T*.
- **Claims and evidence, not a truth score** — sources bind to claims as
  `supports` / `contradicts` / `context` / `reports_allegation`, with independence
  (`independent`, `same_origin`, `syndicated`, `unknown`). "An account posted X" and "X
  occurred" are separate claims. Ten copies are spread, not corroboration; mirrors,
  reposts and syndicated headlines are grouped into one origin cluster.
- **Media checks (`inspect_media`)** — bounded fetch or workspace file, SHA-256, safe
  decode (Pillow with a decompression-bomb guard), `ffprobe` metadata, and `ffmpeg` frame
  sampling at claim-relevant moments, detected scene changes (so a brief inserted clip is
  not stepped over by a uniform grid), and clip boundaries. The exact inspected frame times
  are recorded, and the intervals and audio that were **not** inspected are stated. Frames
  are attached to the model only when the selected route accepts images; what actually
  reached the model is recorded either way.
- **C2PA / Content Credentials** — manifest **presence** is detected in JPEG/PNG; when a
  maintained `c2pa` verifier is installed it is used. `absent` is normal (most media has no
  Content Credentials), `present_unverified` is not a truth claim, and no cryptography is
  hand-rolled. Missing credentials never mean "fake".
- **Answer revisions** — a later correction or update is a new, labelled revision; earlier
  statements stay inspectable, and nothing silently moves the original cutoff.

## Enabling it

Tools are per-Bot and off by default:

```
hutch bot update <name> --tools files,memory,live_search,inspect_media
# or the group: --tools grounding
```

Existing Bots keep their saved tool lists. Strict Offline runs get neither tool; remote
media is refused offline (pass a workspace path instead).

### Configuration (`grounding.json` in the Hutch state directory)

```json
{
  "feeds": ["https://feeds.bbci.co.uk/news/world/rss.xml", "https://hnrss.org/frontpage"],
  "searxng_base": "http://127.0.0.1:8080",
  "searxng_accepts_json": true,
  "bluesky_base": "https://public.api.bsky.app",
  "jetstream_host": "jetstream.us-west.bsky.network",
  "language": "",
  "max_feed_age_hours": 168
}
```

- `feeds` — first-party RSS/Atom feeds; the publisher's declared dates are kept with their
  role and method. Defaults are the BBC World feed and HN's front page feed.
- `searxng_base` — your own SearXNG instance. The adapter mirrors two documented failure
  classes: out-of-range results under a time filter are dropped locally and counted
  (searxng#3358), and engines lost to a time filter are surfaced as `disabled` with a
  single filterless retry whose results are re-validated locally (searxng#3400).
- `jetstream_host` — a Jetstream instance for the `stream` lane (a bounded live window of
  the Bluesky post firehose, filtered client-side by the query). Install the optional
  dependency with `pip install 'hutch[jetstream]'`; without it the lane reports
  `unsupported`. A per-investigation cursor is stored and resumed at-least-once; a
  `CursorTooOld` reply becomes an explicit coverage gap.
- GDELT, Hacker News and the Wikimedia event stream need no configuration; their hosts are
  fixed and fetched through the same SSRF-guarded client.

`GET /api/v1/grounding/config` reports which lanes exist here without claiming a live
connection. No secrets are placed in prompts, URLs, or reports.

## Verified versus unverified (2026-10-11)

| Lane | State |
|---|---|
| RSS/Atom feeds (BBC World, HN front page) | **Verified live** — declared dates parsed and in-frame |
| GDELT DOC 2.0 (news) | **Verified live earlier today; rate-limited during the later run** — the 429 is reported as `rate_limited`, never as zero results |
| Hacker News (Algolia) | **Verified live** — story times parsed |
| Wikimedia EventStreams (events stream) | **Verified live** — 40 events in one bounded read; cursor is the raw `id` array, resumed with `Last-Event-ID` |
| Bluesky public search | **Implemented, blocked from this network** — HTTP 403 is reported as `blocked` |
| Bluesky Jetstream (`stream` lane) | **Verified live 2026-10-11** — 227 events scanned / 8 s window with a matching post retained; cursor resumed to a later window (advanced even when the window matched nothing). Requires `hutch[jetstream]`; the first live read also caught a v2 wire-shape change (nested `payload`, ISO times) that the v1-shaped parser silently ignored |
| SearXNG | **Implemented, needs your instance** — fixture tests cover both failure classes |
| Jetstream cursor/folding contract | **Tested offline** against a local instance: duplicates, `CursorTooOld` gaps, filtered windows, instance-switch rewind |
| Reverse-image / image fact-check | **Unsupported by design** — sending your media to a public matching service is a separate permission this slice does not hold |

## Budgets

One investigation: at most 6 adapters, 4 concurrent fetches, 25 s per adapter, 90 s wall,
40 retained sources, 2 query formulations per adapter. Media: ≤ 8 MB image, 40 MB video,
≤ 6 frames, 1200 px attachments. Streams: ≤ 600 events or 120 s per bounded read. GDELT is
spaced at one request per 5 s per host. These are defaults in code, not tuning claims.

## Safety and privacy

- Acquired text, metadata, captions and file names are **untrusted evidence**. They can
  never change policy, grant permissions, or trigger routines.
- All outbound acquisition goes through the existing SSRF guard (public addresses only,
  every redirect re-checked, the connection pinned to the validated address).
- Media decoding is local and bounded; the panel serves only image derivatives, verifies
  their recorded SHA-256 before sending, and confines paths to the Hutch state directory.
- Your private media is never uploaded to reverse-search services by default; the
  capability reports `unsupported` instead.
- Findings are scoped: "supported in this context", "contradicted / out of context",
  "materially altered (with evidence)", "mixed or disputed", or "insufficient evidence".
  "No manipulation established" is not "authentic".

## Troubleshooting

| Symptom | Meaning | Check |
|---|---|---|
| `blocked` for bluesky | The public AppView refused this network | Not a missing-post finding; try another network or wait |
| `rate_limited` for gdelt | Courtesy limit (1 request / 5 s) | Retry later; Hutch already spaces requests |
| `disabled` for searxng | No instance configured | Set `searxng_base` in `grounding.json` |
| `unsupported` for the stream lane | The optional `websockets` dependency is missing | `pip install 'hutch[jetstream]'` |
| `partial` with a `CursorTooOld` note | The stored cursor is below the instance's lookback floor | Hutch stopped instead of silently skipping; a new window starts from the live tip |
| `zero_results` in a stream window | Nothing matched **in that bounded window** | Check the scanned count in the outcome detail; this is a sample, not the network |
| `zero_results` under a SearXNG time filter | Engines that ignore time filters are disabled by SearXNG | Hutch retried once without the filter; check `detail` and the dropped counts |
| Frames missing in the panel | Extraction failed, or the media details were collapsed | The model brief and panel state which frames were inspected |
| The model "saw" no frames | The selected route cannot receive images | The brief says so and the run records what was transmitted |
