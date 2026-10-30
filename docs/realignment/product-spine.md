# Product spine (2026-10-30)

Status: decision record and contradiction list for the release-readiness run. Sources: `PRODUCT.md`,
README "What is Hutch?", `DESIGN.md` (Overview and Do's and Don'ts), `docs/marketing-site.md` (terminology
contract), `.pipeline/brand/2026-10/BRAND-GUIDELINES.md` (sections 1.2 and 8). Every contradiction below was
read in the working tree at `3bcbe454`; line numbers will drift as P2-P5 land, so treat the ID as the stable
handle and the progress file as the status record.

## 1. What Hutch is

Hutch is a local-first assistant app in development preview. A person asks in a conversation; a named
assistant, using a model route the person chose, does the work on their own computer; anything
consequential stops and waits for their decision; and afterwards they can see what happened, what it cost
(measured or estimated, never presented as an invoice) and repeat it or put it on a schedule. Control state,
history, memory and limits stay on the computer the person controls, and nothing runs that they did not ask
for or schedule. Today it is for people on Linux who are comfortable with a source checkout: there is no
installer, no hosted service and no PyPI package.

Short form, for metadata and the CLI help line: **Hutch is a local-first assistant app: ask, approve what
matters, and review the result, with your data, models and limits on your own computer.** The tagline "Your
bots. Your machine. Your rules." stays as the brand line (`docs/marketing-site.md` allows the pairing).

## 2. The primary loop

1. **Ask.** In Chat, to the main assistant or one the person picks. A schedule or a watched source can also
   ask, but only because the person set it up.
2. **Approve.** A consequential action pauses as a **Needs you** item. One decision binds one exact action.
   Plan-wide approvals do not exist and no surface may offer them.
3. **Result.** The answer plus its evidence: transcript, files, usage and an honest cost estimate. This is
   **Activity**.
4. **Repeat or schedule.** Ask again, hand the work to a specialist as a **Task**, or put it on
   **Scheduled work**.

Configuration (AI services, model routes, skills, limits, runtime) supports the loop and is reached on
purpose; it is never the first screen. Governance (approvals, spend, waiting reasons) stays the loudest
thing on screen (`PRODUCT.md`, principle 2).

## 3. One canonical term per concept

| Concept | Say this in the UI and in user docs | Where the other word stays | Do not use in the UI |
|---|---|---|---|
| The entity a person talks to | **assistant**; the default one is the **main assistant**; one made for a kind of work is a **specialist** | `bot` in the CLI (`hutch bot`), REST paths (`/api/bots`), storage, tests and internal docs; Telegram's own "bot token" | "Bot" as a product noun, "specialist Bot", "Bot-to-Bot" |
| One execution of an assistant | **run** (a History row is "Run 1a2b3c") | `hutch runs`, `/api/runs` | "Work history", "past work", "job" |
| Work, as a mass noun | **work** ("Scheduled work", "keep work moving") | | work as a countable label |
| Work handed from the main assistant to a specialist | **Task** (the Tasks page) | | task as a synonym for run or request |
| A thread with one assistant | **conversation**; the workspace is **Chat** | | "Chat library", "Conversation history", "Chats" as a destination |
| Anything waiting on the person | **Needs you** (drawer, badge, destination) | `approval` is the decided object | "Approvals" as a destination label |
| A recurring trigger | **schedule**; the destination is **Scheduled work** | `cron` only in the editor | |
| What you connect (Ollama, OpenAI, OpenCode) | **AI service** | `provider`, `runtime` in Runtime, `hutch doctor` and advanced panels | "provider" on first run |
| A specific model reachable through a service | **model route** (`ollama/qwen3:8b`) | | display label used as an identifier |
| Connect accounts, apps and keys | **Apps & AI** | | |
| Choose, fit and price routes | **Models** (differs from Apps & AI: connect there, choose here) | | |
| Tokens and currency used | **Usage**; caps are **limits**; an estimate says "estimate" | | "budget" for a hard guarantee |
| Where data lives | **state directory** | | "data dir" |

Titles: `<View> — Hutch` (capital H, em dash, view name first), on the SPA at first paint and after every
route change, and on every server page (`BRAND-GUIDELINES.md` section 8).

## 4. Navigation derived from the loop

| Group | Destinations (in order) | Loop step |
|---|---|---|
| Primary | **Chat**, **Tasks**, **Needs you** | Ask, delegate, approve |
| More | **Activity** (tabs Now / History / Conversations), **Scheduled work**, Skills, Models, Usage, Runtime, **Assistants** | Result, repeat; then configuration |
| Foot | **Apps & AI**, **Settings** | Configuration |

Decisions recorded here (reasons in the right column; none reopens a prompt decision):

| Decision | Reason |
|---|---|
| Merge Conversation history, Activity and Work history into **Activity**; tabs Now / History / Conversations. `#/chats`, `#/overview`, `#/runs` redirect. | Owner decision 1. Today four rows describe overlapping history and nothing says how they differ (S5). |
| Scheduled work stays separate. | It is configuration of future work, not history. |
| Tasks stays primary. | It is delegation, a distinct step of the loop, not history. |
| The assistants destination is labelled **Assistants** everywhere (nav, title, palette). | Every other More row is a noun; "Manage assistants" is the only verb phrase and the SPA already titles the view "Assistants" (`app.js:2161`) and the roster "Assistants" (`index.html:99`). |
| `/models` and `/usage` stay server-rendered but adopt the same shell as the SPA (roster, search, header status, titles). They are not ported into the SPA. | `models.html` is 380+ lines of working no-JavaScript forms; a port exceeds the three-file slice rule and risks regressions for no user-visible gain. One shell is the user-visible requirement. |
| Runtime stays in More. | It is advanced by nature; the executor pill links to it. Keep-reason, not a jargon exception for the first screen. |
| "Needs you" keeps three entry points (button, `#/approvals`, badge). | They open the same drawer (audit S9). P2 only aligns label and `aria-current`. |

## 5. Contradictions

Disposition: **P2** navigation and shell, **P3** start states, **P4** UI-promise sweep, **P5** docs and site
truth, **P6** release, or **Keep** with the reason stated. Status lives in the progress file.

### Definition and titles

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| D1 | `README.md:5`, `README.md:66`, `PRODUCT.md:20`, `pyproject.toml:4`, `src/hutch/cli.py:45`, `AGENTS.md:3`, `website/index.html:7`, `src/hutch/server/static/index.html:6` | Eight statements of what Hutch is: "multi-bot AI assistant", "multi-bot platform", "personal-assistant app", "multi-bot agent platform", "AI assistants", "your personal assistant". A reader of the CLI help, PyPI page and site gets three different products. | P5 for README, `pyproject.toml`, `cli.py:45`, site and `llms.txt`; Keep `AGENTS.md:3` (contributor-facing) but align its first clause |
| T1 | `server/templates/base.html:9` | Server pages render `<X> - hutch` (hyphen, lowercase, brand last) | P2 |
| T2 | `server/static/app.js:2160-2172` | `ROUTE_TITLES` has no `tasks` or `skills`, so the fallback `"hutch"` yields `hutch — hutch`; it says "Assistants" while the nav says "Manage assistants" | P2 |
| T3 | `server/static/app.js:2211`, `server/static/index.html:6` | SPA sets `hutch — <view>` (lowercase, prefix) only on `hashchange`; first paint of every SPA route carries the static title `hutch — your personal assistant` | P2 |
| T4 | `bots.html:3` "Bots", `home.html:3` "Overview", `runs.html:3` "Runs", `connections.html:5` "Connections", `approvals.html:4` "Approvals", `bot_new.html:4` "New bot" | Titles use words the nav does not (Overview vs Activity, Runs vs Work history, Connections vs Apps & AI) | P2 (retitle the live pages, remove the dead ones under X4) |

### Navigation labels

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| N1 | `server/nav.py:18-21`, `index.html:85-88` | Four rows (Conversation history, Activity, Scheduled work, Work history) for overlapping history | P2 (decision 1) |
| N2 | `nav.py:18`, `app.js:2064`, `palette.js:82-83`, `app.js:3505` | One destination, four names: "Conversation history", "Chat library", "Chats", "Chat library" | P2 |
| N3 | `nav.py:21`, `app.js:7054`, `app.js:9236`, `runs.html:3` | One destination, four names: "Work history", "View past work", "All runs", "Runs" | P2 |
| N4 | `nav.py:26`, `index.html:93`, `app.js:2161`, `index.html:99`, `bots.html:3` | One destination: "Manage assistants", "Assistants", "Bots" | P2 (label: Assistants) |
| N5 | `server/static/palette.js:80-93` | The command palette omits Tasks and the assistant manager and uses its own labels and icons ("gear" for Models) | P2 |
| N6 | `index.html:93`, `app.js:2290` vs `nav.py:26` | SPA hides the assistants row until ten assistants; server pages always list it. Same app, two navigation sets | P2 (one rule on both surfaces) |

### Shell and chrome

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| C1 | `templates/macros/sidebar.html:12-41`, `base.html:73-82`, `index.html:122-143` | `/models`, `/usage`, first run and other `base.html` pages have no assistant roster, search or "New assistant", and show Stop all plus a "live" chip where the SPA shows workflow and executor status | P2 |
| C2 | `base.html:74-80`, `app.py:5821`; SPA `tasks.js:97` | The global emergency stop (`POST /api/stop-all`) is reachable only from server-page headers; no SPA code calls it. The only "Stop all" in the SPA stops one Task's assignments, so the same words mean two different scopes | P2 (offer the global stop in the shared header whenever work is running, behind the existing confirm overlay; rename the per-Task button to say its scope) |
| C3 | `macros/sidebar.html:16` vs `index.html:62` | Brand link label `hutch - open main chat` vs `hutch — open main chat` | P2 |
| C4 | `base.html:95` | Server footer prints the absolute state directory (`/home/<user>/...`) into every page and screenshot | P2 (keep version, drop the path) |
| C5 | `models.html:11-20`, `usage.html:8-9` vs `app.js:2125` | Server pages put the title and subtitle in the page body; the SPA puts them in the shell header | P2 |

### Duplicates and dead code

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| X1 | `server/pages.py:154-159` | `/legacy` and `/legacy/` serve the same `index.html` as `/`; the docstring says to delete them | P2 once tests show nothing depends on them |
| X2 | `pages.py:573-586`; links at `models.html:18,181,380`, `home.html:11` | `/legacy/connections` renders a second connections page; `/connections` only redirects, and four links take the extra hop | P2 |
| X3 | `pages.py:221-241`, `pages.py:243-245`, `pages.py:259-279` | `bots_page` builds `views_` then discards it and redirects; `POST /bots` redirects errors to `/bots/new`, which redirects to the SPA and drops the message | P2 (dead body); P4 (POST `/bots`) |
| X4 | `home.html`, `bots.html`, `bot_new.html`, `approvals.html`, `runs.html`, `run.html` | No quoted reference to any of the six exists in `src/` or `tests/` (string search, 0 hits each); the fragments `_home_lists.html`, `_events*.html` and others still have callers | P2: delete after a test proves no caller |
| X5 | `pages.py:286-293`, `usage.html:24` | `/bots/{name}` still renders `bot.html` (83 uses of "bot"), a second assistant-detail UI beside `#/bot/<name>` (`app.js:1897`), reached from the Usage table | P2; verify the no-JavaScript path before redirecting |

### Vocabulary

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| V1 | `app.js` about 93 strings, for example `1687`, `1970`, `2348`, `2374`, `4966`, `5035`, `5464`, `5472`, `5872`, `6890` | "Bot" and "Bots" as a product noun beside "assistant" ("Make a bot", "Share with a Bot", "Bot-to-Bot references", "Specialist Bot") | P2 vocabulary pass with a guard test and a small allowlist |
| V2 | `bot.html` 83, `bot_delete.html` 53, `models.html` 24, `bot_delete_pick.html` 22, `usage.html` 10, `pages_usage.py:39` ("(deleted bot)"), `usage.html:30` ("No bots yet.") | Server pages say "bot" throughout | P2; deletion pages are typed-confirmation flows, so update their e2e assertions in the same slice |
| V3 | `channels.js:12,16` | "Bot token", BotFather | Keep: Telegram's own terms |
| V4 | `cli.py` command groups, `README.md:29` | `hutch bot ...`, "Manage bots" | Keep: CLI contract (`docs/marketing-site.md:26-29`); the first help line follows D1 |
| V5 | `.pipeline/brand/2026-10/BRAND-GUIDELINES.md:23` | Says the operator dashboard calls the entity "bots"; `PRODUCT.md`, `docs/marketing-site.md` and the live nav say "assistant" | P5 (add a reconciliation note; the dashboard is a product surface) |
| V6 | `PRODUCT.md:21`, `palette.js:87` | "task" used generically while the Tasks page means delegated specialist work | P5 for `PRODUCT.md`; Keep the palette search keyword (synonyms aid discovery) |

### Demo-like and evidence-free copy

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| M1 | `README.md:86-93` | A `tidy-downloads` transcript presented as a run, but `hutch init` creates no assistants (`cli.py` init help) and no recorded run backs it | P5 (label it illustrative or replace it with a recorded one) |
| M2 | `app.js:8367`, `pages_usage.py:33` | "Retired mock" and "retired mock route" labels | Keep: truthful labels for legacy rows that may still carry `mock/` routes; `PRODUCT.md` states there is no demo runtime. Test in P4 |
| M3 | Sidebar assistants named in audit S8 | Not in code; rows of a long-lived state directory | Keep: owner action (`hutch bot destroy`) |
| M4 | `website/index.html`, `website/assets/` | Site captions and captures not yet compared with the final dashboard | P5 |

### Governance visibility

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| G1 | Chat studio (`renderChatStudio`, `composer.js`) | A search of `app.js` finds no approval-mode ("Ask first") or limit string in the chat render path; spend appears only in Activity (`app.js:7069`), Usage and Settings. Unverified by screenshot | P2 capture decides; fix is P3 if confirmed |

### Start states

| ID | Where | Contradiction | Disposition |
|---|---|---|---|
| S2 | `models.html:177`, `pages_models.py` vs first run | "No model routes configured" while first run reports OpenCode ready | P3 |
| S10 | first run (`onboarding.html`) | No `hutch doctor` findings, no background-service offer | P3 |
| S11 | per-page empty, loading, error and permission states | Generic `errorState` (`app.js:2227`) only; per-page coverage unverified | P3 |
| S12 | run recovery | Whether a run whose owner process is gone shows as Working was not checked | P3 |

## 6. Not verified

- G1 rests on source search, not on a capture.
- X4 lists templates with no *found* render call; a dynamic render path would not appear in the search.
- No assertion here is a live-model result.
