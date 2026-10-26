# Marketing site claims and evidence

The static site is an alpha preview, not an installation or hosted-service funnel. Its source repository is private and there is
no public package or release. Anonymous calls to action stay on the page and explain availability; they do not point to an
inaccessible private repository, copy commands that cannot work anonymously, or contact the Hutch host. Public links are the
three cited user-report scenarios only. The site loads its CSS, JavaScript, font and images from its own directory and sends no
analytics request. Motion follows the operating system's reduced-motion setting; the page stores no browser preference.

The history description may state that the application has a title-based Chat
library for active, archived, and imported conversations across assistants.
It must distinguish that library from active-chat message search, and must not
claim that archive/imported content is searched by message. Workspace settings
contain new-assistant defaults and a local motion preference; they do not alter
existing assistants or conversations.

## Positioning and terminology

The site's first screen must state the category and deployment model in plain words: Hutch is a
local-first platform for personal AI assistants that run on the reader's own Linux computer. The
approved hero pattern is a warm headline plus a definitional sub-line; the eyebrow names the
category ("Local-first AI assistants · run on your own machine"). The three hero promises are the
product pillars — local state, model and app choice, and ask-first approvals — and each stays
within the capability language below; they are not guarantees.

In public prose the product is "Hutch"; the lowercase "hutch." wordmark is a logo form only. The
single stage term is "private preview" everywhere (footer badge, availability section, metadata);
"private alpha" is retired. The site says "assistant" for the user-facing entity and notes that
the command-line tools call it a bot; internal docs and the CLI keep "bot".

## Capability language

| State shown publicly | Evidence and limit |
|---|---|
| Supported | Linux execution, local SQLite state, up to 100 named recurring tasks per bot with independent timing/prompts, and fixture-tested lifecycle/control paths. A running local supervisor is needed for schedules; tasks on one bot queue under its single-run rule. Actual runs require a configured model route and a running local service or provider connection. |
| Experimental | Configured hosted-provider and local-inference routes; OpenCode Go's user-supplied API-key connection; opt-in Sign in with ChatGPT local token-sharing preview (eligibility for Hutch is unconfirmed, no live account verification, and no provider-enforced output limit); reviewed owner-launched OpenCode coding tasks on Linux in pinned worktrees (`hutch code login` connects a provider in a dedicated Hutch-managed profile; model usage and command permissions remain outside Hutch; no Hutch shell sandbox or automatic branch application); one Hutch local caller and up to eight waiters per state directory; host-gated Offline isolation; opt-in same-bot child tasks under Strict Offline with approval on every request; one explicit user-reviewed coordinator handoff with a durable parent status/result and a durable owner-approved specialist roster that starts empty; an optional, user-selected exact specialist response can be attached as untrusted text to a coordinator follow-up; up to eight current reviewed coordinator facts may be selected for one task, with provider-retention limits disclosed; HTTPS-paired dashboard sessions with revocation; local same-session browser handoff on a Linux desktop; HTTP(S)/WebSocket browser egress pinned by a local proxy. Coordinator handoff does not automatically plan more work or transfer files/history/permissions; selected fact snapshots stay with that task and are not added to specialist memory. A specialist's own enabled memory and workspace may still apply. Same-Bot delegation is serial, task-text-only, private-workspace and subject to the two-run default. Provider/model calls, backend provenance, the visible desktop flow, public browser destinations, non-HTTP browser traffic and physical-device/network access were not verified live for this release. |
| Unavailable | macOS/Windows executor, public source/package, authenticated PTY/physical desktop control, phone browser handoff and Pi as a Hutch-managed Bot runtime. OpenCode is available with an owned private profile; its approved tools run outside the built-in sandbox. |

The response-style section may say that a person can choose Direct, Warm or Dry Wit voice; Auto, Brief,
Standard or Detailed answer depth; and Off, Subtle or Playful humor independently. Humor defaults to off.
Fixed examples are authored text, and changing settings does not call a model. The optional live preview is a
separate user action: it shows a local one-response estimate and uses a fictional sample without conversation
history, tools, skills or workspace. Hosted-provider data terms still apply. These controls guide wording only;
they cannot change tool access, evidence, approval requirements, budgets, output formats or recipients. The
marketing screenshot is a real local settings capture with a fictional assistant and no provider request. It
does not prove provider acceptance, adherence or live answer quality, which remain unverified.

The public support table and FAQ describe chat image input as experimental: the built-in
runtime accepts PNG, JPEG or WebP attachments of up to 1,500,000 bytes each, at most four per
message, staged through the composer's file picker, paste or drop into a visible tray. Staged
images remain in the conversation workspace, travel with every subsequent message until the
owner removes them, and image-only sends are admitted. A built-in route that cannot receive
images is refused at admission with a stated reason before any run exists. On the OpenCode
runtime, images are admitted and verified copies are staged inside the run's own workspace;
the runtime checks the selected model's declared input modalities before the model runs — a
text-only model aborts with the model named, and an unverifiable model aborts as
could-not-be-verified. Preflight cost estimates remain text-only and disclose that staged
images sit outside the estimate; the Vision focus option tunes context handling and does not
enable image delivery. Model-level image inference was verified live on one OpenCode free
vision model by the runtime slice (see the changelog); other providers were not live-verified.
Evidence: `tests/test_chat_vision.py` (including the real free-vision-model test),
`tests/e2e/test_composer.py`, and the composer capability note regression in
`tests/e2e/test_browser.py`.

The site distinguishes local control state from prompt traffic to a selected model and network
traffic generated by tools. Local mode limits model routes but keeps configured tools online;
Hybrid permits hosted routes. Offline is a host-gated experiment. Its worker probe and local
fixture-provider request passed, but the separately running model service is outside Hutch's
worker boundary and may itself use the network. Native Ollama admission uses current memory
measurements and backend-reported resident allocations; fit remains estimated. Other local
protocols lack validated memory admission. Hutch reserves token and price estimates before
eligible hosted calls, but provider invoices can differ. Bubblewrap is a Linux namespace sandbox,
not a VM; migrated bots remain unsandboxed until an operator enables the setting.

## Cost, context and routing claims

The approval section may say that a multi-request **Needs you** queue puts the soonest decision deadline first, then high risk and
actions that leave the machine; it may describe due-soon and high-risk counts/filters plus requests that leave the machine, and state
that each request is still decided one at a time. It must not claim bulk approval, automatic approval, a measured triage-time improvement, or that every
allowed action is safe. This is backed by the approval-triage browser matrix, axe results, and the queue measurements under
`docs/realignment/approval-triage-2026-10-22/`; those are fixture checks, not a user study.

The site may say that Hutch offers distinct warning, approval-pause and estimated admission-ceiling controls. It must not call the
estimate a provider-enforced hard cap. For OpenRouter, a configured strict USD ceiling requires a fresh, endpoint-aware quote; when
the metadata is stale, unavailable, or contains no qualified priced endpoint, Hutch blocks the call. A non-strict view can show a
labeled stale quote or reviewed local price. Cost disclosure should say that provider tokenization and billing remain authoritative.

Bot settings support explicit manual mappings from seven task roles to exact `provider/model` routes, selected for one chat message.
Site copy may describe this as operator-selected routing; it must not imply an automatic quality classifier, a capability guarantee,
provider pinning, or measured cost savings. Fallback means the selected model is unavailable; escalation means repeated quality
failures. The app does not silently choose a different Hutch route.

Studio's review sheet may describe the selected route, current draft, bounded recent conversation context, selected skills,
and spend-policy state.
The estimate is a preview: conversation state can change before admission, provider tokenization and billing can differ, and an
OpenRouter route may select another eligible endpoint. Do not present the estimate as an invoice or provider-enforced ceiling.
The public feature and FAQ copy was checked in Chromium at desktop, tablet and phone sizes. Source site captures and the Studio
preflight screenshots are under `docs/realignment/artifacts/assistant-first-ui/marketing/` and
`docs/realignment/artifacts/cost-guardrails-2026-10-11/`; captured viewport, source hash, browser errors and overflow results
are recorded in their adjacent validation JSON files.

Hosted summaries ask first by default. Owners can explicitly opt into automatic summaries or disable them; every paid summary has its
own quote and reservation, context-reduction checks are bounded, and original history stays accessible. The page should not promise
lossless summarization or that an approval wait currently releases the owning run worker.

Workspace copy may say that fresh per-run folders are the default, and that an operator can choose a private Hutch-managed folder per bot
or a validated existing folder. It must also say that managed folders survive bot deletion and are excluded from database-only backup;
the site must not imply that files are automatically moved or copied when the setting changes.

The site may say that Hutch creates documents locally - PDF, DOCX, XLSX, PPTX, CSV, JSON, Markdown, YAML and ZIP bundles -
from reviewed content specifications, stores them in Hutch's own document store on the user's machine as immutable versions with
recorded SHA-256 hashes, and serves downloads through authenticated local routes that verify size and hash before every response.
Copy may state that downloads do not expire with the chat or run that produced them, that revisions create new versions while older
versions remain downloadable, and that previews are labelled: page images for PDF (rendered from the stored version), extracted
structure or text for other formats, and approximate layout renders for office formats only when LibreOffice is installed on the
host. It must not claim Word/Excel/PowerPoint desktop compatibility, malware-free status, cloud delivery, redaction, or
password-protected-input support; those are named limits in `docs/file-formats.md`. The capability evidence trail is
`docs/file-formats.md` plus failure classes E1-E15 in `docs/realignment/evidence-ledger.md`.

The site may say that files created through Hutch's `write_file` tool are downloadable from their originating run as verified
snapshots (up to 4 MB per file and 16 MB per run). The Studio composer menu can browse saved text files and saved tool output
from runs attached to that same conversation. An owner can also explicitly add one verified file reference to a selected other
chat and revoke it later. The source bytes remain with the original run; Hutch does not copy them into the receiving workspace or
add them to that chat's model context. This is a per-file grant, not a general shared library. Shell-created files are not
automatically attached to chat.

The Bot-setup workflow may say that Hutch derives an editable professional display name and stable local address from the purpose
written by the user. This is a deterministic browser-side suggestion, with no additional model request; the owner reviews both values
before confirming creation. Do not imply that a suggested name changes the Bot's permissions, standing instructions, or authority.
From any visible user message in chat, the owner can choose **Make a bot** to reuse that exact request; the top-bar setup path
uses the latest request. The owner can optionally select up to eight earlier user-authored messages from that same conversation.
Later messages, assistant replies and other conversations stay excluded. The review names each selected message and warns that saved
text may be sent to the Bot's model on future runs. Selected conversation text grants no tools, accounts, or permissions. The built-in
workspace coordinator can also provide an optional, tool-free experimental rewrite of the current purpose using that exact source and
only explicitly selected earlier user context (one response per request). The owner must edit/apply the result; it cannot create a Bot or change its authority.
The coordinator's configured route/fallback and normal usage limits apply, hosted providers may retain the submitted text, and live
draft quality is unverified. Multi-round clarification and generative naming remain unimplemented. Do not describe this as an automatic
configuration change or as verified model quality. When a validated workspace/source-chat route exists, the first New Bot screen
creates a no-tool, ask-first Bot from the described purpose or selected request. **Customize** opens the full model, workspace,
tool, memory, schedule, limit, browser-handoff and review controls. If no model route exists, the UI requires the user to select one;
it must not imply or silently choose a hosted provider. In an active chat the latest user request is already the starting
instruction; **Make a bot** binds the exact selected user message. The owner reviews the request and suggested name without
restating the task and may edit the instructions if needed. Creation saves the Bot and starts no run.

The site may describe saved requests as a searchable local library. Saving requires a review of the first user request; using an entry
fills a chat draft and does not send or start work. The library is in local SQLite state and included in database backups. JSON
template download/import remains an explicit local file workflow. Do not imply public links, team sharing, typed placeholders, or
that saved prompt text is sent to a provider before the owner sends the chat message.

The Connections support table may list Google Calendar, Outlook Calendar, and Outlook Mail as experimental local integrations that
require operator OAuth configuration and Linux Secret Service. Google Calendar lookup is read-only by default; guest-free event creation
is an owner-configured experimental preview that requests a broader Google scope and exact per-event approval. Outlook Calendar lookup
uses `Calendars.ReadBasic`; optional guest-free event creation uses a separate `Calendars.ReadWrite` sign-in and one-calendar Bot grant,
then requires exact approval and readback verification. Microsoft scope is account-wide and can change or delete events, while Hutch
exposes creation only on the selected calendar. Do not describe either provider as publicly supported while OAuth verification and live
account consent remain unverified. No provider account or consent verification has been performed. For Outlook Mail, Hutch requests
delegated `Mail.Read` and returns bounded message previews to a Bot explicitly granted one mailbox. A separate Outlook `Mail.Send`
preview has a Connections setup, but no live account verification; public copy must keep it experimental. Microsoft consent is
account-level, and Hutch cannot revoke it itself.
Gmail may be described only as an owner-configured private preview: it requests restricted, account-wide `gmail.readonly`, returns bounded
sender/subject/date/snippet previews, and grants the Hutch tool only to built-in Bots with loopback Local model routes and no hosted
fallback. Google's permission remains broader than Hutch's Bot grant. Public release is unavailable pending applicable Google scope
verification and any required security assessment. No live provider account or consent has been verified. Do not imply public support for
Gmail, calendar writes, mail changes, or provider-side approval.

The coordinator workflow may say that a completed coordinator answer can be prepared as a task for one selected Bot. The user must
choose the specialist, review its saved settings, edit the goal, optionally add an expected deliverable and constraints, and explicitly
confirm. The original request stays linked to the proposed brief and reviewed handoff. Only the reviewed brief, constraints and facts
selected for that task cross into the new chat;
the specialist's own enabled memory/workspace may still apply. The coordinator can receive one exact specialist answer only when
the user selects and attaches it to a follow-up; Hutch preserves its source and treats it as untrusted. Label this handoff
experimental and do not imply automatic multi-step planning, resumable checkpoints, live provider verification or file transfer.
The owner-approved roster is a durable local control over who may receive new tasks; it starts empty and does not change an
approved Bot's tools or access.

The product preview is a real first-run application capture with an empty state directory. It
shows the request field beside the AI service Hutch found on that machine, or the next connection
choice when none is ready; it does not imply that a provider call succeeded. It contains no seeded
bots, conversations, runs, approvals, credentials, or provider output. Older fixture-generated
images have been removed from `website/assets/captures`; their source artifacts remain under
`docs/realignment/artifacts/` as historical test evidence and are not linked or copied to the
public site.

## User-report scenarios

The site links to three public issues as acceptance scenarios, not prevalence evidence:

- [OpenClaw issue 138499](https://github.com/openclaw/openclaw/issues/138499): one report of a timed-out scheduled task remaining marked as running and delaying restart. Hutch keeps cancellation visible until owned execution exits and fences expired ownership before recovery.
- [Open WebUI issue 30055](https://github.com/open-webui/open-webui/issues/30055): one report that a full-screen mobile call overlay hid an already-delivered approval. Hutch keeps approval state and decisions in the responsive app and fixture-checks phone layouts; this is not physical-device certification.
- [Open WebUI issue 31656](https://github.com/open-webui/open-webui/issues/31656): one report that mobile menu focus opened a text field and keyboard unexpectedly. Hutch's menu has focus handling and restoration checks; this is not a screen-reader audit.

The copy does not claim external spend guarantees, universal process containment, working
external harnesses or public installation. Delegation claims apply only to the bounded built-in
Strict Offline path and must disclose per-call approval, serial child execution and the absence of
parent-workspace file transfer. It describes action decisions in chat and the
cross-bot Needs you drawer; Activity and run history remain monitoring tools, while Fleet is
progressive navigation at ten bots. Ten is an operator-selected product heuristic, not a
measured user-research threshold.

## Screenshot provenance

`website/assets/captures/setup-desktop.webp` (1440×1000) and `setup-phone.webp` (390×1200) show the actual application with a
new, empty temporary state directory, refreshed on 2026-10-26 after the first-run intro was reworked. They contain no seeded bots, conversations, runs, approvals,
credentials, provider output or external action. The desktop, tablet, phone and compact-phone source captures, browser versions,
timestamps and source hashes are retained under `docs/realignment/artifacts/no-mock-setup/`; visual validation is recorded in
`docs/realignment/visual-validation.md`. These images are screenshots of the app, not evidence of a live provider call. The mascot is an original Blender render
(`scripts/render_hutch_agent.py`), shipped as `website/assets/hutch-agent.webp` plus a 7x3 look-at-cursor frame grid in
`website/assets/agent/`; it is decorative product art, not an application screenshot.

Source merges do not regenerate these image files. After a UI change, run
`.venv/bin/python docs/realignment/capture_first_run.py`, convert the new desktop and phone PNGs to the corresponding WebP assets,
then run `npm run build:css` to stamp the new content hashes into `website/index.html`. Recapture and inspect the marketing page at
desktop, tablet and phone sizes afterward. A content hash refreshes browser caches only when the image bytes have also been updated;
it does not make an old screenshot current by itself. The separate application/marketing contact sheets are generated by
`docs/realignment/capture_navigation.py`; set `HUTCH_IMAGE_PYTHON` to a Python with Pillow and `PLAYWRIGHT_BROWSERS_PATH` to the
installed browser cache before running `.venv/bin/python docs/realignment/capture_navigation.py`. Run that utility too when refreshing
integrated navigation evidence, then inspect `docs/realignment/artifacts/navigation/`.

Before changing product copy, compare it with `docs/realignment/ledger.md`, `docs/realignment/evidence-ledger.md`,
`docs/realignment/visual-validation.md`, and the current provider/support matrix in `docs/adr/0005-providers-auth-and-subscriptions.md`.

## Discovery metadata and structured data

- `<title>` and the meta description lead with the category and the word "local-first" and state the private-preview status; they must stay in step with the hero's definitional sub-line.
- The `SoftwareApplication` JSON-LD block carries name, description, category, operating system, version, MIT license, `isAccessibleForFree`, a feature list and `dateModified`. It has no `url`, `screenshot`, `offers` or publisher while the site has no public domain or public project identity to cite.
- The `FAQPage` JSON-LD block mirrors the visible FAQ exactly; `test_structured_data_and_discovery_metadata_match_the_page` fails when a question exists in one place and not the other. Generate the schema block from the markup instead of editing it by hand.
- The FAQ comparison item may name Open WebUI and OpenClaw in prose without linking to them, limited to verifiable architectural differences (where work runs, governance defaults, approval model). It must not claim superiority, benchmarks or community-scale facts.
- `website/robots.txt` allows all crawlers and deliberately carries no `Sitemap:` line: the directive requires an absolute URL and no public domain has been chosen. `website/llms.txt` restates the core product facts for answer engines inside the same claims envelope as this document.
- Deferred until a public domain exists: canonical URL, `og:url`, an absolute `og:image`, and `sitemap.xml`.

## Visual system and assets (Oct 2026 rework)

One token source (`website/tokens.json`) compiles to `website/tokens.css` via `scripts/build_site_tokens.py`, which validates
references, cycles, duplicate names and the declared text/background contrast pairs, and fails on output drift (`--check`).

| Asset | Provenance |
|---|---|
| `website/assets/agent/f*-p*.webp` (7x3 look-at-cursor frames) | Original Blender render: `scripts/render_hutch_agent.py` (bpy 5.0.1, Cycles CPU, 96 samples, denoise, transparent film; no chroma keying). Blue palette; an `--palette emerald` variant exists in the script. The body follows a pointer turn at 34%, the visor/cap/face group at 72%, pivoting at the neck. Post: 16px alpha-blur glow pass, unified 620x880 canvas, webp q82. Regenerate with the venv noted in the script docstring. |
| `website/assets/hutch-agent.webp` | Copy of the centre frame (`f3-p1`), used as the still hero and CTA artwork. |
| `website/assets/captures/setup-*.webp` | Sanitized captures of the redesigned app from an empty temporary state directory (`docs/realignment/capture_first_run.py`, desktop 1440×1000 and phone 390×1200); no mock run, personal data, provider request or external effect. |
| `website/assets/captures/response-style-*.webp` | The Response style panel from the real assistant settings (Behavior pane), cropped to the embedded 586×383 and 340×544 by `docs/realignment/capture_response_style.py` against a temporary state directory (2026-10-26): the fictional `Design Partner` has no model route, request or output, and Warm / Detailed / Off are saved through the real controls before the capture. The examples beside it are authored HTML text. |
| `website/assets/fonts/geist-latin-var.woff2`, `geist-mono-latin-var.woff2` | Geist and Geist Mono (SIL OFL, © Vercel in collaboration with basement.studio), Latin variable subsets made with `pyftsubset`, self-hosted; licence in `OFL-geist.txt`. |

Pointer behaviour is an enhancement: it starts only on `(pointer: fine)` devices with at least 4 cores, no `saveData`, and no
reduced-motion preference; the frame grid is fetched on idle after first paint, and any failed frame leaves the still image in
place. Reduced motion, touch, and no-JS visitors get the static centre frame.

## Build (Tailwind v4 + DaisyUI v5)

The marketing surface is Tailwind + DaisyUI layered on the brand token source:

- `website/src/input.css` — Tailwind v4 entry. DaisyUI v5 loads with an explicit component
  include list (`button, badge, card, navbar, footer, table, collapse, alert, link, menu`)
  and a custom `hutch` theme mapped to the current design contract: emerald `#34d399`, 8px
  controls, 12px panels, 100px chips, and one dark theme.
- Rebuild with `npm install` (once) then `npm run build:css`, which compiles `website/app.css`
  and minifies the Hutch-specific `website/styles.css` source into `website/styles.min.css`.
  It stamps each local asset reference in `index.html` with an 8-char content hash so a
  cached sheet can never outlive its build. Both compiled files are committed, so the page
  stays a static, no-build surface at runtime: no external requests, no toolchain needed to
  serve it. In the current build, `app.css` is 51,665 bytes, editable `styles.css` is
  42,310 bytes, and its served minified output is about 35.6 KiB. The 40 KiB transfer budget
  applies to `styles.min.css`; deployment gzip/Brotli compression is not part of the local
  transfer measurement.
- `website/styles.css` holds only hutch-specific pieces — hero weave, proof chrome, code
  window, architecture diagram, receipts/availability tables, footer base, motion.
- `website/tokens.css` remains the generated source of truth for brand/semantic values;
  `tests/test_site_tokens.py` checks that every `var(--token)` in `styles.css` resolves, and
  that the compiled `app.css` is present with the theme and components in place.

## Reference decisions (supplied design set, Oct 2026)

Adopted: window chrome for product proof (traffic-dot trio, centred monospace title, status chip); the receipts as a real
data table (# / Source / Reported failure / hutch answer / Evidence) with fixed columns, hairline rows, right-aligned
evidence pills and a mobile card stack; icon + title + copy feature cards in a three-up grid; a separately headed
"How a run is wired" architecture block (SVG diagram on desktop, readable list on phones) kept apart from the feature cards;
numbered instructional workflow cards with a title and concise caption; a model-route pill row; the poster wordmark
sized to sit fully inside its column (no sliced strokes) behind a dimensional subject with exactly one front glyph; a
monospace spec line under the hero subject; and syntax-coloured code windows (chrome bar, coloured keys, terminal status bar).

Rejected: purple aurora gradient heroes, gradient display type, warm-beige editorial palettes, collage-of-floating-cards
backgrounds, and the 24-48px translucent container look. Also rejected after review: a page-level emerald hero wash (removed
in favour of the artwork's own contained glow), a box-in-box "limits" panel with an orphan card (now a plain hairline list),
a half-empty wide use-case card (now three even columns), a container wrapped around the receipts table, and a poster wordmark
cropped past the scene edge. The pinned brand contract (emerald accent, 0px controls / 8px panels / 100px chips, one dark
theme) governs.

## Verification (Oct 2026 rework)

- `tests/test_site_tokens.py`: token compilation, contrast pairs, drift.
- `tests/e2e/test_website.py`: anonymous assets/CTA checks, no-JS readability, no external requests, reference-pattern presence
  (table shape, icon cards, architecture block, route pills), agent frame set, distinct code styling, dialog drawer
  focus/Escape, reduced-motion visibility, reveal watchdog, tab keyboard operation, no-mock claims, first-run screenshot provenance,
  and zero horizontal overflow across phone, tablet and desktop sizes.
- Screenshot review at 1440 and 390 (hero, proof chrome, receipts table, workflow, runs + architecture, control, use cases,
  availability, FAQ, CTA), plus pointer-swap verification left/right and a measured check that the hero wordmark fits its
  column (about 18px slack each side).

The files under `docs/realignment/artifacts/marketing-top/` are historical captures, not current design evidence. Their
`capture.json` records the 2026-10-08 source revision and an HTML hash that no longer matches `website/index.html`; do not use
their screenshots as a representation of the current landing page. The full-site audit and refreshed source-pinned captures are
recorded under `docs/realignment/artifacts/ui-audit-2026-10-20/`; source changes do not update screenshots automatically.

The adaptive-style marketing check is captured in `docs/realignment/artifacts/persona-marketing-2026-10-11/`.
It records the current HTML/CSS/image hashes and Chromium viewport measurements for 1440×1000, 768×1024,
720×480 (effective CSS width for a 200% reflow check), 360×844 and 320×800. Its authored voice/depth examples are checked as static content; the FAQ is opened in
the browser; all page requests are same-origin GETs; no provider or inference request occurs. The component-only
screenshots suppress the sticky header and skip link to prevent fixed elements from being composited across a
tall capture. The phone/desktop app images remain unaltered crops of the retained actual-app screenshots.
The verified page reports zero horizontal overflow and no page errors at those widths. This remains a static
marketing check, not live model-quality evidence. The headless runner cannot apply a native browser zoom gesture.

Known gaps: no physical-device or screen-reader session; contrast is computed for declared token pairs, with rendered surfaces
checked by eye at the two review widths; the frame grid is untested on very low-end GPUs.
