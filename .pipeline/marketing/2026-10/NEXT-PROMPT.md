You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first; GitHub https://github.com/K-Arthur/hutch is the only public entity surface — the site has no live domain yet, owner-confirmed 2026-10-28).

Read only:
1. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/HANDOFF.md (decisions incl. D-01=Option A approved, D-04 allow-all, B-06 manifest owner; next slice = S-a)
2. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CLAIM-REGISTER.md (section "F-01 draft replacement wording — llms.txt" is the APPROVED text to apply; review log shows human sign-off 2026-10-28)
3. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CONTENT-MAP.md §2 slice S-a (acceptance criteria + rollback)
4. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/FINDINGS.md (F-01, F-06 detail if needed)

Session type: slice S-a — IMPLEMENTATION (Phase 5). Apply the approved llms.txt repair. This is the first slice that touches a product file.

Write scope: /home/kevina/CodingProjects/hutch/website/llms.txt ONLY (plus .pipeline/marketing/2026-10/{CHANGES.md,EVIDENCE.md,HANDOFF.md,NEXT-PROMPT.md} updates).
Out of scope: every other file — especially downloads.json (P2-04), robots.txt (D-04 resolved), README.md, index.html, src/**, app/**, and the other agent's uncommitted files (src/hutch/server/**, app/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore — never stage; use `git show HEAD:<file>` for reads).

What to do:
- Read current website/llms.txt; apply the three approved changes verbatim (llms.txt:3 clause, llms.txt:9 line, add the Repository line per CLAIM-REGISTER F-01 section). No other rewording.
- Verify acceptance (all five AC in HANDOFF "Next slice"): grep 0 hits for "private preview"; GitHub URL present; fact parity with README:5,16-22 + index.html:780,793; `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/audit_site.py` exit 0 with llms_txt.mentions_github=true; commit touches website/llms.txt + .pipeline only.
- Run `npm run check:agent` before reporting complete.
- No visual gate needed (plain-text machine file, not rendered). No build needed (no CSS/HTML change).
- Commit locally: `seo(slice-s-a): repair llms.txt availability facts + add GitHub link`, staging website/llms.txt + .pipeline/marketing/ only. Do not push.
- Update EVIDENCE.md (create from template if absent) with the AC→evidence mapping; update CHANGES.md, HANDOFF.md, NEXT-PROMPT.md (next slice = S-b, which must open with the Phase 3 front-end gate per DECISION.md).

Do NOT start S-b. Do not paraphrase the approved wording. Do not push/deploy/merge.

Acceptance (all must be true, with evidence paths):
- website/llms.txt matches the approved replacement; `grep -in "private preview" website/llms.txt` returns nothing.
- audit_site.py exit 0; crawl-report.json `llms_txt.mentions_github` = true; all facts in llms.txt trace to README/site pointers in the claim register.
- git show of the commit contains only website/llms.txt + .pipeline/marketing/2026-10/**.
- EVIDENCE.md maps each AC to its evidence; CHANGES.md records the slice; HANDOFF.md points at S-b.
- Not pushed.
