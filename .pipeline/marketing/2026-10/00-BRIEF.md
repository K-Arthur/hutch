# 00 - CAMPAIGN BRIEF (session 10: post-launch CI/deploy verification + owner-gated discovery steps)

- Product / one-liner: Hutch - local-first, MIT-licensed multi-bot AI assistant platform ("Your bots. Your machine. Your rules."), development preview, Linux-first. Repo: https://github.com/K-Arthur/hutch · site: https://k-arthur.github.io/hutch/
- Repo / branch / commit at session start: /home/kevina/CodingProjects/hutch · main · local = origin/main = `577e1154` (record commit of session 9). Other workstream's uncommitted tree present (src, app, tests, package files, AGENTS.md, .gitignore, CONTRIBUTING.md) — never staged.
- Artifact dir: .pipeline/marketing/2026-10/
- Session type: review (session 10). Adapter: NEXT-PROMPT.md written by session 9.
- Human request this session (via adapter): FIRST verify the CI run on the final pushed commit; diagnose only failures traceable to session-9 changes. Then, human available: confirm the three session-9 defaults (pushed main, github.io host, v0.1.0 pre-release) and take owner-gated steps (social preview upload, Search Console/Bing properties, Dependabot triage record, custom-domain decision, badge row after green CI).
- Authority: commit locally; push docs/evidence updates to main under the standing session-9 authority. No force-push, no dependency upgrades as marketing, no custom domain without the owner.
- Write scope: .pipeline/marketing/2026-10/**, docs/discoverability.md, docs/marketing-site.md, README.md, website/**. Out of scope: product code, dependency upgrades, the other workstream's uncommitted tree, history rewrite.
- Budget: verification session — no product edits expected; at most README badge row if CI is green; read only files named in the adapter plus site head/badge lines if edited.
- AI answer targets: Google AI Overviews/AI Mode, ChatGPT Search, Perplexity, Copilot, Gemini, Claude.
- Success criteria:
  1. CI run on `577e1154` identified by run id with recorded conclusion; failures (if any) triaged to session-9 changes vs other workstreams.
  2. First Pages deployment of the record commit confirmed live (run id + live URL check).
  3. The three defaults confirmed with the human; owner-gated steps either executed or recorded as blocked-on-owner with exact instructions.
  4. Badge row updated only if CI is green and the human confirms no host change.
  5. Evidence, CHANGES, HANDOFF, NEXT-PROMPT updated; claim register unchanged unless a verified fact flipped.
