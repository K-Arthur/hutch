# Page audit: behaviour, redundancy and consolidation (2026-10-30)

Owner request: apply the Models-page check to the other pages (does the page answer its own question, is
there one place to write each thing, is any copy false, is any control dead), say whether behaviour needs to
change, and say which pages should be consolidated to cut redundancy. Method: a seeded workspace (three
assistants, one main; a done run, a failed run, an interrupted run and a demo-era failure) on a real server
and Chromium 153, every destination captured at 1440 and 360 px with its visible text and controls, plus a
read of the code behind each. Console and page errors across all 17 captures at both widths: none.

Status words: **done** (changed and tested in this run), **recommended** (clear case, not yet changed),
**decision** (changes the information architecture the product spine fixed; waits for the owner).

## 1. Verdict per page

| Page | Should answer | Verdict | Finding and action |
|---|---|---|---|
| Chat / home | What do I say, to whom, on which model | Works | Welcome, composer and model chip are truthful. **Done:** a person with nothing set up now starts on a disclosed starting model (section 3). |
| Tasks | What did my main assistant hand to specialists | Keep | Fresh state reads "No tasks yet. Ask your main assistant to prepare one and assign it to a specialist", fine once specialists exist. Overlaps Activity Now (both show live work). **Decision** D2. |
| Needs you (drawer) | What is waiting for me | Inconsistent | The drawer lists **approvals only** ("0 approvals") while Activity's "Needs you" section lists approvals, questions **and failed runs**. Same label, two sets. **Recommended:** one list, shown in both places. |
| Activity > Now | What is running, what needs me | Works, one defect | **Done:** an interrupted run said "Open the transcript for the failing step", advice for a fault that is not there. It now says the job was cut short and what to do (an in-flight action warns that it may have happened and does not suggest simply asking again). Redundant: two stat tiles ("Assistants", "Tasks today") and a "Usage details" accordion repeat the roster and the Usage page. **Recommended** removal; pinned by `test_design_system.py` and `test_browser.py`, which are at their frozen caps. |
| Activity > History | Past runs | Works | Filter labels are human ("Completed", "Didn't finish", "Waiting on you"); demo-era failures carry a "Legacy" label and are out of "Needs you". |
| Activity > Conversations | Find a chat | Works | One search, three scopes. |
| Scheduled work | What recurs | Works | Honest empty state with one action. Third copy of schedule management: the assistant's Schedule tab and Runtime's "Queue and automation". **Decision** D3. |
| Runtime | Is this machine ready | Mixed | Machine/service/instance facts plus automation (watched sources, multi-step jobs, queue). The background-service offer appears on **three** surfaces (first-run setup check, Settings > Installation, this page). **Decision** D3. |
| Skills | What can my assistants learn | Truthful gap | "Available to install (10)" were the person's own skills from `~/.claude/skills` and `~/.agents/skills`, labelled only `user`. **Done:** the section now reads "Found on this computer", names the folders Hutch looks in and shows each skill's path. Second store beside Catalog with the same trust model. **Decision** D1. |
| Catalog | Where do I get a ready-made assistant | Works | Publisher, version, hash and permissions on every entry; creating a copy goes through the normal setup review. |
| Models | Which service is ready, which assistant uses what | Fixed earlier | One default writer (Settings), no duplicate add form, advanced routing collapsed and open when configured. |
| Usage | Where did tokens and money go | Works | Owns spend and budgets. Cost also appears in Activity's accordion and Models' price table. **Recommended:** Usage owns it; the others link. |
| Apps & AI | What is connected | Noisy | Five cards read "Not enabled in this build" on the main list. Truthful, but dead weight above the working ones. **Recommended:** collapse them under "Not available yet". |
| Settings | Defaults, appearance, About you | Works | One writer for the new-assistant default; "Installation" duplicates Runtime. **Decision** D3. |
| Assistant detail | Configure one assistant | Heavy | Eight tabs and about 30 controls on the first tab (eight colour swatches, shapes). Fine for tuning, wrong as the way to create. **Done:** creation no longer goes through it (section 3). |

## 2. Consolidation: what overlaps and what to do

Ten sidebar destinations is more than the product has distinct questions. Overlaps found, strongest first:

| # | Overlap | Evidence | Proposal | Status |
|---|---|---|---|---|
| D1 | **Skills and Catalog are two stores** | Both discover from folders, both hash-pin, both stay inert until reviewed and trusted, both install "from a local folder". Two top-level rows, two vocabularies ("Install" vs "Create a copy"). | One **Catalog** destination with views *Assistants* and *Skills* (the Activity tab pattern: a views list, one tab strip, legacy hashes redirected). `#/skills` keeps working as a redirect. | **decision** |
| D2 | **Tasks, Needs you and Activity are three views of work** | Tasks = delegated assignments; Needs you = approvals; Activity Now = running plus needs-you plus failures. | Activity gets a *Tasks* view; the sidebar "Needs you" row stays as the quick drawer but lists the same set as Activity's section. | **decision** |
| D3 | **Runtime, Scheduled work and Settings > Installation** | Background-service offer on three surfaces; automation split between Runtime and Scheduled work. | *Scheduled work* absorbs watched sources, multi-step jobs and the queue ("Automation"); machine and service health moves under Settings > Installation next to the setup check; Runtime row retires. | **decision** |
| D4 | **Cost in three places** | Usage page, Activity accordion, Models price table. | Usage owns it; Activity and Models link. | **recommended** |
| D5 | **Models and Apps & AI both say "add or repair a service"** | Models now links to Apps & AI for that. | Keep both: Models answers "which assistant uses what", Apps & AI holds accounts and keys. Revisit only if Models stays read-only. | no change |

Net effect if D1 to D3 are accepted: ten destinations become seven (Chat, Needs you, Activity, Catalog,
Automation, Models, Usage), with Apps & AI and Settings in the footer. They are reversible tab merges using
a pattern already shipped for Activity, but each touches the nav model, the palette, page titles and about
a dozen pinned tests, so they are held for an explicit yes rather than slipped into a release-candidate run.

## 3. Selecting a model and creating an assistant (owner request)

The original path was: four wizard steps (purpose, model with runtime / route / routing mode / workspace,
tools with a starting point and schedule, review), a model route typed or picked from a datalist, and, when no
route was ready, a three-page detour through `/onboarding` that ended at "Saved on this machine. Hutch has
not connected to this route yet". A person with no setup could not create an assistant in one step.

**Done (verified):**

- One shared decision, `starter-route.js`, used by first run, the new-assistant setup and the Models
  detection panel. Most private first: a ready model on this computer, then a provider the person already
  connected, then a **free** OpenCode model. An unconnected OpenCode profile exposes only free models; once
  connected, only models whose id says free count, and a paid model is never offered as a free start.
- A hosted starting model **always carries a notice**: it leaves this computer, free hosted models can keep
  or learn from what is sent, use it for nothing private, and where to change it (Settings sets the default
  for new assistants; an assistant's AI model tab changes just that assistant). The route is only
  *preselected*: nothing is saved until the person creates the assistant, which keeps Hutch's explicit
  approval model (AGENTS.md, hard rules).
- The quick setup names the model ("Uses the selected AI service: glm-flash-free") and creates in one step.
- A second assistant starts on the main assistant's route, with no detection call and no notice.
- Customisation is intact: "Fine-tune the details" still opens runtime, route, routing mode, workspace,
  tools, schedule and limits; Settings and the AI model tab still change any route.

**Still open:** if OpenCode is not installed, no free starter exists and the `/onboarding` chooser remains the
fallback; its three routes record intent only. Replacing that detour with a single "install or connect one of
these" page is the next simplification. The README should say the free starter needs the OpenCode CLI on
`PATH`.

## 4. Other findings recorded, not changed

- Assistant identity files (`identity/assistant-<id>.json`) are not removed by governed assistant deletion.
  Erasure works on directories and writes a manifest inside the target, so a per-assistant file needs
  `identity/<id>/` first; a small change to the deletion plan, deliberately not made in passing.
- Activity's two KPI tiles and usage accordion (above).
- Connections' five "Not enabled in this build" cards (above).
