# DECISION — assumptions & front-end gate

## Assumptions (Phase 0)
- A-01: `website/` is the only public marketing surface. Basis: adapter discovery. Resolve in Phase 1.
- A-02: No analytics installed on site. Basis: not spotted in file listing. Resolve in Phase 1.
- A-03: No sitemap.xml. Basis: not in website/ listing (robots.txt + llms.txt exist). Resolve in Phase 1.
- A-04: Site deploy target unknown (CI workflows don't reference website/). Resolve in Phase 1.
- A-05: English-only. Basis: all site files are English. Resolve in Phase 1.
- A-06: This campaign does not touch `src/hutch/server/**`, `app/**`, `package.json`, `pyproject.toml`, `AGENTS.md`, `CONTRIBUTING.md`, `.gitignore` — another agent holds them uncommitted (git status 2026-10-28).

## Research decisions (Phase 0, 2026-10-28)
D-01..D-08 recorded with evidence and falsifiers in `RESEARCH.md §7`. Summary: governed-local-first positioning (pending human sign-off in Phase 2); llms.txt kept as agent affordance only; FAQPage markup kept with zero rich-result expectation; robots allow-all for search/user bots with training bots as a human call; entity source order README → site FAQ → llms.txt; no mention-chasing; measurement via GSC + Bing AI Performance + dated prompt set; BLOCKER D-08 public domain unknown.

## Post-session inputs
- 2026-10-28 (human): site has no live domain yet. B-01 resolved as pre-launch status; slices must stay domain-independent until a domain/host is chosen. GitHub repo is the sole public entity surface; treat README as the primary off-site discovery asset.

## Front-end necessity gate (Phase 3 — deferred)
Not run this session. No UI work planned in Phase 0. (Note for Phase 3: the user's standing design-workflow gate requires online UI/UX research + route approval before any rendered change; public Figma previews via web research are the sanctioned path since the Figma MCP is unavailable.)

## Authority
- Commit locally only. No push/deploy/merge without explicit human instruction (confirmed by user 2026-10-28).
