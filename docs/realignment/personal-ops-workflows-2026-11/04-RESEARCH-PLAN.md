# Research plan: personal ops, coding, family workflows, shipped workflows, automations and multimodal pipelines (2026-11)

Mandatory before designing each phase. Record all findings in
`docs/research/2026-11-personal-ops-workflows/`, extending (never duplicating)
`.pipeline/personal-operations/2026-10/{00-BRIEF,RESEARCH,COMPETITIVE-ANALYSIS,FAILURE-ANALYSIS}.md`,
`docs/research/complaints.md`, and `docs/research/offerings-and-failures.md`.

For every source, record: URL, publication date, access date, evidence grade (`VERIFIED`,
`OBSERVED`, `COMPLAINT`, `HYPOTHESIS`), the specific claim relied on, and what design requirement
(`POW-R*`) it produced. If a page is gated by a CAPTCHA or anti-bot wall, stop and record it as
unreachable (`AGENTS.md` guideline); use primary docs, GitHub issues, or archived threads instead.

## A. Owner-supplied benchmark URLs (re-verify and extract multimodal/UX/edge-case gaps)

1. `https://github.com/K-Arthur/hutch` - current public README, positioning, issue tracker, and
   any drift between the public repo description and `HEAD`.
2. `https://openclaw.ai/showcase` - community showcase patterns and self-reported failure stories
   (including the runaway WhatsApp message loop and automation reliability complaints).
3. `https://x.com/jdrhyne/status/2012778049406742632` (`@jdrhyne`) - 15+ agent fleet across
   machines, daily roll call, delegated coding workers (Codex/OpenCode), Discord/chat control plane.
4. `https://x.com/danpeguine/status/2012565160586625345` (`@danpeguine`) - personal OS with daily
   briefings, importance-scored timeblocking, meeting-transcript weekly reviews, family school
   deadlines, invoice/receipt triage.
5. `https://x.com/georgedagg_/status/2012119327147798753` (`@georgedagg_`) - voice-guided
   production debugging, deployment config fix, redeploy and PR creation while away from a laptop.
6. `https://x.com/dreetje/status/2012535486401671588` (`@dreetje`) - single chat interface
   controlling mail, Beeper messages, orders, reminders, GitHub issues, PDF recaps, voice input, and
   a read-only vs read-write 1Password vault split.
7. `https://x.com/davekiss/status/2008994096736817624` (`@davekiss`) - complete website rebuild
   (Notion to Astro, 18 posts migrated, Cloudflare DNS switch) executed remotely from Telegram.
8. `https://x.com/stevecaldwell/status/2007616854689280196` (`@stevecaldwell`) - family meal
   planning system in Notion, weather-aware weekly dinner schedules, aisle-sorted grocery lists, and
   recurring morning/evening household digests.

For each of the 8 sources, verify what `.pipeline/personal-operations/2026-10/RESEARCH.md` already
captured and extract the *remaining* gaps specifically around:
- **Multimodal inputs/outputs:** voice notes while walking, receipt/invoice photos via Telegram,
  PDF/deck recaps, generated charts/SVGs, and migrated markdown/media posts.
- **Mobile & away-from-desk supervision:** how the human verifies a diff, approves a deploy/DNS
  change, or checks a morning briefing from a phone without opening a laptop.
- **Household/shared state conflicts:** what happens when two people edit a grocery list or receive
  a school-deadline reminder.

## B. Competitor & adjacent offering analysis (what works vs what fails)

Research how current products handle these five workflows and where users report they break:

1. **Personal ops & daily briefings:** Motion, Reclaim AI, Sunsama, Akiflow, Todoist AI, Apple
   Reminders/Intelligence, Notion AI, Lindy.
   - *Failure modes to mine:* auto-scheduler reshuffling whole calendars on one 15-minute slip
     ("calendar jitter"), hallucinated tasks from casual emails, timezone shifts when traveling,
     silent sync failures after OAuth token expiry, "AI summary" hiding an overdue deadline.
2. **Family & household workflows:** Cozi, Hearth Display, AnyList, Bring!, Paprika, Mealime, shared
   Notion/Apple Reminders spaces, Home Assistant dashboards.
   - *Failure modes to mine:* duplicate grocery items ("milk" vs "2% Milk" vs "milk " added every
     week), one family member's private tasks leaking into the household view, reminder notification
     fatigue causing spouses to mute the bot, recipe/meal plans ignoring local weather or calendar
     busy nights.
3. **Coding orchestration & remote fixes:** Claude Code, OpenAI Codex CLI/cloud, OpenCode, Cursor
   background agents, Devin, GitHub Copilot Workspace.
   - *Failure modes to mine:* agent reports "fixed and tested" when tests were skipped or mocked,
     orphaned git worktrees consuming tens of gigabytes, background processes surviving after timeout,
     mobile/voice coding flows pushing unreviewed config changes to production with no rollback.
4. **Shipped workflows & deliverables:** n8n, Zapier Central, Make, Relay.app, Gumloop, ChatGPT
   Code Interpreter / Canvas, Claude Artifacts.
   - *Failure modes to mine:* generated PDFs/CSVs/XLSX with truncated rows or broken formulas
     presented as complete, expired download links in chat transcripts, no central place to find
     files generated across past runs ("where did that report go?").
5. **Daily automations & webhooks:** OpenClaw Automations (2026.8+), n8n schedules/webhooks,
   GitHub Actions cron, systemd timers, Home Assistant automations.
   - *Failure modes to mine:* silent cron deaths, DST double-fires or skips, webhook replay storms,
     edited schedules with no revision history ("who changed this cron and when?"), runaway loops
     when an automation triggers its own event source.
6. **Multimodal intake pipelines:** Telegram/WhatsApp bots with vision & Whisper STT, paperless-ngx,
   Expensify/Dext receipt scanning, local VLMs (`gemma4`, `qwen2.5-vl`, `llava`) and Whisper/speech
   models.
   - *Failure modes to mine:* Whisper hallucinating "Thank you for watching" on silent voice notes,
     vision models misreading receipt totals or DD/MM vs MM/DD dates, attachments silently dropped
     when switching to a text-only model, prompt injection embedded in image text or PDF hidden
     layers.

## C. Required research outputs (`docs/research/2026-11-personal-ops-workflows/`)

1. `00-GAP-AUDIT.md` (Phase 0): current codebase audit against G01-G14 and multimodal seams.
2. `01-SOURCES.md` (Phase 1): dated table of all primary docs, showcase links, issues and advisories.
3. `02-FAILURES-AND-COMPLAINTS.md` (Phase 1): clustered failure modes classified as
   `fixable-in-Hutch`, `mitigable`, or `external-limit`, each paired with a concrete test scenario.
4. `03-REQUIREMENTS-AND-DECISIONS.md` (Phase 1): numbered requirements (`POW-R1`...) and architectural
   decisions that Phases 2-9 trace back to.
5. `06-VALIDATION-LEDGER.md` (updated in Phases 2-9): dated record of every real-stack test,
   migration check, multimodal run, and Playwright visual capture.

