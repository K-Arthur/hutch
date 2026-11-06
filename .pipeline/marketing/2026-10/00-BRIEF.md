# 00 - CAMPAIGN BRIEF (session 11: CI flakiness check + CI badge)

- Product / one-liner: Hutch - local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. Repo: https://github.com/K-Arthur/hutch · site: https://k-arthur.github.io/hutch/
- Repo / branch / commit at session start: origin/main `adddfbfd` (2026-10-29). Local main was 15 commits AHEAD of origin at first check and 118 at the last check (the product workstream committed continuously), while its HEAD moved (`cb8ca349` -> `f0551b8b`). Campaign work ran in detached worktree `.worktrees/marketing-s11` at origin/main; the product tree was not staged, merged or pushed.
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: review (session 11). Adapter: NEXT-PROMPT.md written by session 10.
- Human request this session (via adapter): FIRST check CI run `40837883068` (the adapter's flakiness data point); if a full CI run on main is green, add the CI badge to the README badge row, keep the release badge on v0.1.0, and push the docs change. Then re-offer the owner-gated steps.
- Authority: commit + push docs/evidence to main under the standing session-9/10 authority. No force-push. No product code/tests, no dependency work.
- Write scope: .pipeline/marketing/2026-10/**, README.md. website/**, docs/discoverability.md and docs/marketing-site.md were allowed by the adapter but not needed (no rendered site change).
- Out of scope: product code and tests, dependency upgrades, the other workstream's far-ahead unpushed commits and dirty tree, PR #11, history rewrite.
- Budget: verification session; one README line + campaign artifacts + CI evidence. Read only adapter files plus README and the workflow trigger.
- AI answer targets: Google AI Overviews/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude.
- Success criteria:
  1. Run `40837883068` identified by conclusion; explain why it can/cannot serve as the flakiness data point.
  2. Any newer full CI run on main identified by run id + conclusion.
  3. CI badge added only if a full CI run on main is green; release badge stays on v0.1.0.
  4. Badge verified: HTTP 200, SVG says passing, link target is the workflow.
  5. EVIDENCE/CHANGES/DECISION/HANDOFF/NEXT-PROMPT updated; claim register unchanged.
  6. Owner-gated steps re-offered and their disposition recorded.
