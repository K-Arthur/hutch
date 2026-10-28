# EVIDENCE — slice S-a (llms.txt entity-surface repair) — 2026-10-28

Phase 6 proof per acceptance criterion. Slice scope: `website/llms.txt` (3 line edits) + this artifact dir.

## AC → evidence map

| # | Acceptance criterion (CONTENT-MAP §2 S-a / NEXT-PROMPT session 3) | Result | Evidence |
|---|---|---|---|
| 1 | `grep -in "private preview" website/llms.txt` → 0 hits | PASS (exit 1, no output) | shell run 2026-10-28 in repo root; output recorded in session transcript: `grep-exit=1` |
| 2 | llms.txt states source public + MIT + GitHub URL, using the human-approved F-01 wording verbatim (CLAIM-REGISTER §"F-01 draft replacement wording") | PASS | `git diff HEAD -- website/llms.txt` shows exactly 3 changed lines: :3 (availability clause), :9 (status line), :25 (Repository line replacing the old site-canonical tail); full file re-read confirms approved sentences character-for-character |
| 3 | Fact parity with README:5,16-22 and index.html:780,793 (C-05 development preview, C-11 no installers/sign-up, C-12 Linux-only) | PASS | README:5 ("development preview", MIT, public), README:19 ("no PyPI release or public desktop download; Linux source checkout"), index.html:780 ("Desktop installers are not available yet… no hosted sign-up"), index.html:793 ("MIT-licensed development source is public on GitHub. There are no packaged desktop installers or hosted sign-up today") — all read this session; llms.txt new text matches each fact |
| 4 | `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0 with `llms_txt.mentions_github=true` | PASS | exit 0 (shell); full report captured at `evidence/audit/s-a-crawl-stdout.txt` (stderr empty at `s-a-crawl-stderr.txt`): `llms_txt = {status: 200, mentions_github: true, lines: 26}` |
| 5 | No regression in the rest of the crawl vs phase-1 baseline | PASS | s-a-crawl-stdout.txt: ua_parity 6/6 UAs (default, Googlebot, Bingbot, OAI-SearchBot, ClaudeBot, PerplexityBot) 200 with identical 97639 bytes; anchors 10/10; both JSON-LD blocks parse; FAQ parity 20/20 exact, 0 mismatches; only 404s remain the known domain-gated security.txt + sitemap.xml (F-02/F-11) |
| 6 | Commit touches website/llms.txt + .pipeline/marketing/2026-10/** only | PASS | `git show --stat` of the S-a commit: 1 product file (website/llms.txt, 3+/3-) + pipeline artifacts; the other agent's 78 dirty files untouched (never staged) |
| 7 | `npm run check:agent` before reporting complete | FAIL — pre-existing, NOT caused by this slice | 1 context-hygiene violation naming `tests/test_commit_attribution.py` (419 lines, committed in `bee491d5` before this campaign session; not in this diff); tool-contracts PASS (40 tools); constitution PASS (3 roles/14 rules); agent-map --check FAIL stale `.ai/repo-map.generated.md` which is untracked other-workstream tooling (`?? .ai/`) and contains 0 references to llms.txt or .pipeline. Recorded as blocker B-07 with owner = git-attribution/agent-map workstream |

## Notes
- The committed phase-1 baseline (`evidence/audit/crawl-report.json`, `mentions_github: false`) is intentionally NOT overwritten: audit_site.py prints to stdout; the S-a report is captured alongside it under an `s-a-` prefix so the dated baseline stays intact for comparison.
- Visual gate: N/A by design — llms.txt is a plain-text machine file, never rendered (NEXT-PROMPT session 3, pre-authorized). No build required (no CSS/HTML change).
- Real-query check: deferred with the AI-answer baseline (RESEARCH §5 prompt set) to slice S-d — requires a live domain (B-01). No invented queries were used as evidence.
