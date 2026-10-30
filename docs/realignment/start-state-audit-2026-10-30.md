# Start-state and completeness audit (2026-10-30)

Status: evidence and plan. One defect is fixed (commit `06887b15`); the rest are queued below with
acceptance criteria. Nothing here claims a live-provider, packaged-install or multi-OS result.

## Method

- Fresh, empty state directory (`HUTCH_STATE_DIR` under the session scratchpad), `hutch serve` on
  port 8799, working tree of `main` including the uncommitted brand/UI changes (the version a user
  running from this checkout sees).
- Playwright, Chromium revision 1243, 1440x900 and 360x800, all 15 sidebar destinations (`/`,
  `#/chat`, `tasks`, `approvals`, `chats`, `overview`, `schedules`, `runs`, `runtime`, `skills`,
  `/models`, `/usage`, `#/bots`, `connections`, `settings`). Recorded per route: title, visible text,
  console errors, failed requests, horizontal overflow, screenshots viewed for home, Models, Needs you.
- Result that holds: 0 console errors, 0 failed requests and 0 px horizontal overflow on all 15
  routes at both widths. The first-run page reports a real OpenCode detection (8 model options,
  concrete route), not canned data.
- Not run: any live model call, an end-to-end first task on a real route, a populated-state pass,
  a screen-reader pass, axe-core.

## Findings

| ID | Finding | Evidence | State |
|---|---|---|---|
| S1 | The approval card offered "For this plan (20)" and then said the action was "granted to the plan"; plan grants were never implemented, so it granted one use. The API accepted and ignored `plan_scope`. | `_approval_card.html`, `pages.py` decide route, `app.py` `ApproveRequest`, `approvals.py` docstring | Fixed in `06887b15`; page route returns 422 for `choice=plan`, API returns 422 for `plan_scope != 0`; two regression tests |
| S2 | Two pages disagree about whether a model route exists. Home says OpenCode is ready with 8 options; `/models` says "No model routes configured." Home reads live detection (`onboarding.route_options()`); Models lists only saved routes (`configured_model_routes` kv plus bots' models). | Screenshots `home-1440x900`, `models-1440x900`; `models.html` empty branch; `pages_models.py` | Queued (P1) |
| S3 | Page titles are inconsistent: `hutch — hutch` on Tasks and Skills; server pages use `Models - hutch` / `Usage - hutch`; brand guideline section 8 specifies `<View> — Hutch`. | `report.json` titles; `BRAND-GUIDELINES.md` | Queued (P1); already noted by the brand handoff as "title drift" |
| S4 | `/models` and `/usage` are separate server-rendered documents with different header chrome (Stop all, "live" chip, no search or roster) and a different nav label ("Manage assistants" vs the SPA's "Assistants"). `/legacy/connections` and `/bots/delete` are further server pages. | `nav.py`, `pages.py`, screenshots | Queued (P1/P2) |
| S5 | Four destinations describe overlapping history: Conversation history, Activity, Work history, Scheduled work, plus Runtime. Nothing in the UI says how they differ. | `nav.py` MORE group | Queued (P2), needs a product decision |
| S6 | `static/redesign-preview.html/.js` (279 KB bundle built from `src/hutch/web/preview/fixtures.ts`, "synthetic") is untracked now. `app.py` mounts all of `static/`, so committing it would serve a fixture-driven page at `/static/redesign-preview.html` (it is `noindex` and unlinked). | `app.py:7256` static mount; file headers | Queued (P0): keep it out of the served tree or gate it, with a test |
| S7 | A "Nothing runs until you ask." line floats alone in the right column of the first-run page. Cosmetic; judged from one screenshot only. | `home-1440x900.png` | Unverified as a defect |
| S8 | The sidebar bots named in the report (Repo Sweeper, Research Briefing, Tidy Downloads) are not seeded by current code: `hutch init` creates no bots and no startup path creates one. Their taglines come from the removed starter seeding (commits `25a7aaef`, `19cbcd96`), so they are most likely rows in a long-lived state directory. A "Working" row would be a run the system never recovered. The state database was not opened (AGENTS.md forbids it). | `cli.py init`, `rg create_bot`, git history | Needs the owner to check `hutch status` / `hutch runs`; removal is available through governed `hutch bot destroy` |
| S9 | Retracted: `#/approvals` is not a wrong page. It opens the real "Needs you" drawer (0 approvals) over the first-run screen. | `approvals-1440x900.png` | Not a defect |

Process findings that block a clean release state:

- The working tree carries 206 uncommitted entries from two earlier sessions (brand slices 7A-7C,
  and a models/forms/usage change set). Several of them are mixed into the same files (`app.js`,
  `index.html`, `base.html`, `studio.css`).
- The agent audit tooling is not part of the repository: `scripts/audit_context_hygiene.py` is hidden
  by `.git/info/exclude`, and HEAD's `package.json` has no `check:agent`; AGENTS.md and the dirty
  `package.json` reference commands that a fresh clone cannot run. Its current output (5 findings:
  `bot_deletion.py` 1067 lines, `tests/test_bot_deletion.py` 771, `tests/test_commit_attribution.py`
  419, `cli.py` +2 and `store.py` +12 over their frozen caps) is therefore not attributable to HEAD.
  `bot_deletion.py` is from the committed whole-Bot deletion work and genuinely exceeds the cap.
- Known failing checks in that tree, recorded by the other sessions: `tests/test_workflow_usage_budget.py`
  (dirty, unrelated failures) and `tests/e2e/test_design_system.py::test_persona_live_preview_is_explicit_isolated_cancellable_and_responsive`
  (40 px vs 44 px run button). Not re-run here.

## Comparison: start states of Hermes Agent, OpenClaw and Grok Bot

Evidence grades: **[repo README]** fetched 2026-10-30 (states what the page says, not tested);
**[search]** search-result summary, unverified; **[vendor/news]** marketing or press.

| Start-state element | Hermes Agent | OpenClaw | Grok Bot | Hutch today |
|---|---|---|---|---|
| Install | one-line script on Linux/macOS/WSL2, PowerShell script on Windows [repo README] | installer script, or `npm install -g` [repo README] | hosted app, no install [vendor/news] | Linux source checkout only; no PyPI, no installer published (README) |
| Guided setup | `hermes setup` wizard; `hermes setup --portal`; offers to import from `~/.openclaw`, `~/.claude`, `~/.codex`, `~/.cursor` with a preview [repo README] | installer starts onboarding; `openclaw onboard --install-daemon` "verifies model access, creates the workspace, and configures the Gateway" [repo README] | role inferred from the first message, workflow suggested [single vendor blog, conflicting sources] | first-run page: first request, detected AI service panel, setup review; verified in screenshots, end-to-end first run not run |
| Model/provider choice | `hermes model`, `/model` mid-session; validation not stated [repo README] | verified during onboarding [repo README] | bundled | Models page, model switcher, `hutch doctor`; Models page and first-run disagree (S2) |
| Diagnostics | `hermes doctor` (checks not stated) [repo README] | `openclaw gateway status` named; `openclaw doctor` appears only in a search summary [search] | none found | `hutch doctor`; whether the first-run UI surfaces it was not checked |
| Background service | gateway service install [search] | daemon as launchd/systemd user service [repo README, search] | cloud | `hutch service install` (systemd user unit); not offered in the first-run flow (README documents it as a CLI step) |
| Messaging reach | Telegram, Discord, Slack, WhatsApp, Signal, Email gateway [repo README] | WhatsApp, Telegram, Slack, Discord and others; unknown senders paired by default [repo README] | desktop, phone, group chats of bots [vendor/news] | dashboard plus paired phone supervision; no messaging gateway claimed in the README |
| Memory / skills / schedules | agent-curated memory, agentskills.io-compatible skills, natural-language cron [repo README, search] | workspace skills, registry [search] | routines, bots trained by observation [vendor/news] | per-bot reviewed memory, Agent Skills `SKILL.md` packages, IANA-timezone schedules (README) |

Reading the table honestly: Hutch's safety model (ask-first approvals, exact-action binding, typed
deletion, spend reservations) is at least as developed as the others describe. The gaps are in the
path to the first success and in release packaging, not in feature count:

1. No one-command install and no import from an existing agent (Hermes, OpenClaw have both paths).
2. The first-run flow does not offer to install the background service or run `hutch doctor`.
3. Pages that should agree do not (S2, S3, S4); a new user meets these within the first two minutes.
4. The path from first request to a verified first completed task has not been exercised end to end
   on a real route in this audit (needs a live route; not run).
5. Messaging-channel reach is a deliberate non-goal today; if it becomes a goal it is a feature
   slice, not a polish item.

## Plan, in order

| Slice | Work | Acceptance |
|---|---|---|
| P0 | Land the orphaned tree: verify it, decide which audit scripts become tracked (or drop the references), keep `redesign-preview.*` out of `static/`, commit in focused groups. | Clean `git status`; full non-browser suite green at the merged tree with exact counts; `check:agent` runs from a fresh clone; the two known failing checks fixed or recorded with an owner |
| P1 | Start-state coherence: unify titles (S3); Models page acknowledges a detected-but-unsaved service with a one-click "use this route" (S2); align `/models` and `/usage` chrome and labels with the SPA shell or move them into it (S4). | New e2e module on a fresh state dir: no contradictory route statements, one title format, 0 console errors, 0 overflow at 1440/900/360 |
| P2 | Information architecture: decide whether Activity, Work history and Conversation history merge; label what remains. | Decision recorded; nav tests updated; no destination that duplicates another without a stated difference |
| P3 | First-success path: offer `hutch doctor` results and the background-service step inside first run; exercise first request to completed task on a configured route. | Recorded run on a real route with evidence, or an explicit "not run" |
| P4 | Release packaging: install path (PyPI or installer), signing, hosting. | External prerequisites; not attempted here |

## Sources

- Hermes Agent: [repository README](https://github.com/NousResearch/hermes-agent), [documentation](https://hermes-agent.nousresearch.com/docs/)
- OpenClaw: [repository README](https://github.com/openclaw/openclaw) (search results were mostly forks and mirrors)
- Grok Bot: [press coverage](https://www.thebridgechronicle.com/story/news/nation/xai-grok-bot-ai-teammate-everyday-work-tasks), [vendor blog](https://www.mindstudio.ai/blog/grokbot-xai-agent-app) (the sources disagree on what the product is; treat as low confidence)

## Next-run prompt

> Read `docs/realignment/start-state-audit-2026-10-30.md`. Start with P0: verify the uncommitted tree
> (full non-browser pytest, `npm run build:css` determinism, `scripts/audit_emoji.py`), keep
> `redesign-preview.*` out of the served `static/` directory, then commit in focused groups with explicit
> paths and no AI-attribution trailer. Then P1 with a new fresh-state e2e module. Do not open any
> `*.db*` file or state directory.
