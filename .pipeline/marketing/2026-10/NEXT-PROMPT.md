You are continuing the marketing/discoverability campaign for Hutch (local-first, MIT-licensed multi-bot AI assistant platform, development preview, Linux-first; GitHub https://github.com/K-Arthur/hutch is the only public entity surface — the site has no live domain yet, owner-confirmed 2026-10-28).

Read only:
1. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/HANDOFF.md (decisions incl. S-a-01..03; B-07 repo-gate red is pre-existing/other-workstream; next slice = S-b)
2. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/DECISION.md (P2-01 = D-01 Option A approved: KEEP warm H1, ADD "MIT-licensed · open source · Linux" trust row above fold; P1-03 site is dark-only by design; P1-06 focus-state capture required)
3. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CONTENT-MAP.md §2 slice S-b (acceptance criteria + rollback)
4. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/CLAIM-REGISTER.md (C-02/C-03/C-05 wording for the trust row; C-24 dateModified trigger; prohibited-claims table)
5. /home/kevina/CodingProjects/hutch/.pipeline/marketing/2026-10/FINDINGS.md (F-08 description length, F-12 trust words below fold)

Session type: slice S-b — IMPLEMENTATION (Phase 5), but it MUST OPEN with the Phase 3 front-end gate because it touches rendered HTML (website/index.html).

Split the slice into two verifiable steps within this one session:
  Step 1 (copy-only, no gate needed beyond parity): meta description 198→≤160 ch keeping "Development preview." intact (F-08). The JSON-LD description (index.html:23) is separate text and must stay untouched.
  Step 2 (rendered change — FULL gate first): D-01 Option A trust row "MIT-licensed · open source · Linux" above the fold (F-12). Before implementing: (a) answer the five Phase 3 questions in DECISION.md; (b) run the standing design-workflow research requirement (web research for ≥3 concrete inspected examples from ≥2 sources; Figma Community scouting via web search + image reading since the Figma MCP is 403 — do not ask the user to re-auth Figma); (c) present 3-4 scope-sized route options with a recommendation and WAIT for human route approval (question tool) before writing any HTML. If approval does not arrive, ship Step 1 only and hand off.

Write scope: /home/kevina/CodingProjects/hutch/website/index.html + .pipeline/marketing/2026-10/** only.
Out of scope: every other file — especially llms.txt (approved state), downloads.json (P2-04), robots.txt (D-04), README.md, src/**, app/**, and the other agent's uncommitted/untracked files (src/hutch/server/**, app/**, tests/**, package.json, pyproject.toml, AGENTS.md, CONTRIBUTING.md, .gitignore, .ai/, .githooks/, docs/agent-workflow.md — never stage; use `git show HEAD:<file>` for reads).

What to do:
- Step 1: trim the meta description (index.html:7) to ≤160 ch, no mid-sentence cut, keep "Development preview." and the local-first/Linux/MIT facts per C-01..C-05. Then update JSON-LD `dateModified` (index.html:37) to today per C-24's registered trigger (any visible-copy change — the head description is visible in SERPs/shares).
- Step 2 (after route approval): add the trust row using existing site tokens only (open-props/Tailwind already in website/; NO new dependencies, NO third-party requests — input.css:5 contract). Full visual gate: `npm run build:css:site` if any CSS changes, `uv run --frozen --no-sync python .pipeline/marketing/2026-10/evidence/audit/capture_site.py` for desktop+mobile+narrow captures (dark-only by design), PLUS a real focus-state capture (P1-06 gap), then LOOK at the images and record observations in EVIDENCE.md. Re-run audit_site.py (exit 0, FAQ parity 20/20, UA parity 6/6).
- Run `npm run check:agent` and report result honestly: it is currently RED for B-07 (pre-existing, other workstream: tests/test_commit_attribution.py 419 lines + stale untracked .ai/ map) — report the same single violation, do NOT fix those files.
- Commit locally (one commit): `seo(slice-s-b): trim meta description + add above-fold trust row` (or description-only variant if Step 2 not approved this session). Stage website/index.html + .pipeline/marketing/ only. Do not push.
- Update EVIDENCE.md (AC→evidence incl. screenshot observations), CHANGES.md, CLAIM-REGISTER.md (C-24 dateModified row refresh), HANDOFF.md, NEXT-PROMPT.md (next slice = S-c social cards, domain-independent part: og:image asset).

Do NOT start S-c. Do not flip the H1 (Option A keeps it). Do not add any claim not in the register. Do not push/deploy/merge.

Acceptance (all must be true, with evidence paths):
- Meta description ≤160 ch, "Development preview." intact, JSON-LD description unchanged; dateModified updated to the edit date.
- If Step 2 approved+done: trust row visible above the fold on desktop AND mobile captures; images inspected and observations recorded; audit_site.py exit 0; FAQ parity 20/20; focus state captured on a real control.
- git show of the commit contains only website/index.html + .pipeline/marketing/2026-10/**.
- EVIDENCE.md maps each AC to its evidence; CHANGES.md records the slice; HANDOFF.md points at S-c.
- Not pushed.
