# CLAIM REGISTER — Hutch — 2026-10-28 (session 3, Phase 2)

Types: capability, performance, security, privacy, pricing, licence, platform, compatibility, maturity, social-proof, benchmark, availability.
Status: approved · approved-with-qualifier · pending-evidence · prohibited · stale.
Verifier default: campaign (Claude research lead) 2026-10-28, via RECON.md (session-2 measurements) unless noted. Evidence pointers were re-checked this session where the file was read; pointers sourced from RECON carry "(via RECON §n)".

## Register

| ID | Claim (exact wording/pattern) | Type | Evidence pointer | Verified by / date | Owner | Refresh trigger | Status | Pages |
|---|---|---|---|---|---|---|---|---|
| C-01 | "local-first" / "runs on your own computer" (control state local) | privacy | index.html:7, 279; README:5; llms.txt:3,5 | campaign 2026-10-28 | campaign | storage architecture change | approved | /, llms.txt, README |
| C-02 | "MIT-licensed" | licence | LICENSE; README:5, 224-226; index.html:27, 793, 983; llms.txt:11 | campaign 2026-10-28 | human | licence change (would be rebrand-level event) | approved | /, llms.txt, README |
| C-03 | "runs on your own Linux computer"; Linux host required | platform | index.html:7, 25, 823, 977; README:20 | campaign 2026-10-28 | campaign | platform support change | approved-with-qualifier (Linux only, today) | /, llms.txt, README |
| C-04 | version "0.1.0" | maturity | index.html:26 (JSON-LD) = index.html:955 (footer) = pyproject.toml:3 (`git show HEAD:` verified both states) | campaign 2026-10-28 | human (release owner) | any release/version bump | approved-with-qualifier (triangulated; no release tag exists yet — README:16-18) | / |
| C-05 | "development preview" (stage) | maturity | index.html:7, 780, 954-955; README:16-22; llms.txt draft (below) | campaign 2026-10-28 | human | stage change at release | approved | /, llms.txt, README |
| C-06 | "assistants ask before important actions"; hard-denied shell classes; no bulk approval | capability | index.html:31 (JSON-LD featureList), 287; FAQ index.html:844; llms.txt:13 | campaign 2026-10-28 | campaign | approval-model change | approved | /, llms.txt |
| C-07 | "Control state stays local; a hosted model receives the prompts and context Hutch sends to it; network tools connect to their own destinations" | privacy | FAQ index.html:871-872; index.html:812; llms.txt:5 | campaign 2026-10-28 | campaign | any new outbound data path | approved-with-qualifier (qualifier sentence MUST stay adjacent) | /, llms.txt |
| C-08 | "estimated spend ceilings, usage reservations … provider billing stays authoritative; estimates are not an external spending guarantee" | pricing | FAQ index.html:911-912, 915-916; JSON-LD index.html:33; llms.txt:14, 23 | campaign 2026-10-28 | campaign | budget mechanism change | approved-with-qualifier (never stated as guaranteed limit) | /, llms.txt |
| C-09 | Factual contrast: Open WebUI = self-hosted chat front-end; OpenClaw = broad-access personal assistant; Hutch = governed by default | capability | FAQ index.html:851-852; RESEARCH §1 (competitor self-descriptions fetched 2026-10-28) | campaign 2026-10-28 | campaign | QUARTERLY re-verify of both competitors' self-description + any incident refresh | approved-with-qualifier (factual contrast only; never "better than") | / |
| C-10 | "the software itself is free … no subscription, hosted tier or usage fees of its own" | pricing | FAQ index.html:847-848; JSON-LD isAccessibleForFree index.html:28; llms.txt:11 | campaign 2026-10-28 | human | pricing model change | approved-with-qualifier (provider costs stated adjacent; never "free forever") | /, llms.txt |
| C-11 | "no packaged desktop installers or hosted sign-up today" | availability | index.html:780, 793; README:19; llms.txt:21 (draft preserves) | campaign 2026-10-28 | human | first installer release | approved | /, llms.txt, README |
| C-12 | "macOS/Windows executors … are unavailable" | platform | index.html:811; README:20-21 | campaign 2026-10-28 | human | executor implementation | approved | /, llms.txt, README |
| C-13 | Model routes: Ollama, llama.cpp, LM Studio, OpenAI, Anthropic, OpenRouter, OpenAI-compatible endpoints, OpenCode | capability | JSON-LD index.html:32; llms.txt:5; README:10-13 | campaign 2026-10-28 | campaign | route added/removed | approved | /, llms.txt |
| C-14 | Proof capture is a real application capture, dated 2026-10-23, no provider call made | social-proof (product evidence, not testimony) | index.html:316-335 (via RECON §6; capture conditions stated on page) | campaign 2026-10-28 (via RECON) | campaign | any new capture (re-date) | approved | / |
| C-15 | "private preview" stage term (llms.txt:3 first clause) — REMOVED | maturity | fixed 2026-10-28 in slice S-a: llms.txt:3 now "…The source is public and MIT-licensed on GitHub; there are no packaged desktop installers." (C-05 wording); no "private preview" occurrence remains (grep 0 hits, EVIDENCE.md AC1) | campaign 2026-10-28 | campaign | any regression reintroducing the term | approved (resolved, S-a) | llms.txt |
| C-16 | "Status: development preview. The MIT-licensed source is public on GitHub; there are no packaged desktop installers and no hosted sign-up." (llms.txt:9) | availability | fixed 2026-10-28 in slice S-a: llms.txt:9 replaced per approved F-01 wording; parity with README:5,19 + index.html:780,793 re-verified (EVIDENCE.md AC2/AC3) | campaign 2026-10-28 | campaign | any availability/status change | approved (resolved, S-a) | llms.txt |
| C-17 | "- Repository: https://github.com/K-Arthur/hutch — the README and the repository's evidence ledger are the canonical summary of current capabilities." (llms.txt final line) | availability | fixed 2026-10-28 in slice S-a: approved F-06 line added as llms.txt tail (replacing the old site-canonical sentence — decision S-a-01); audit crawl mentions_github false→true (EVIDENCE.md AC4) | campaign 2026-10-28 | campaign | repository URL change | approved (resolved, S-a) | llms.txt |
| C-18 | Chat image input: PNG/JPEG/WebP, up to 4 per message, 1.5 MB each; vision-capable route required | capability | index.html:798; FAQ index.html:863-864; llms.txt:15 | campaign 2026-10-28 | campaign | any limit change | approved | /, llms.txt |
| C-19 | Schedules: IANA-timezone recurring tasks catch up after sleep while the service runs; nothing runs while off | capability | JSON-LD index.html:35; FAQ index.html:883-884; llms.txt:16 | campaign 2026-10-28 | campaign | scheduler behavior change | approved | /, llms.txt |
| C-20 | robots.txt Allow-all for search/user-fetch bots | machine | robots.txt:1-2; RESEARCH §4 (per-engine docs) | campaign 2026-10-28 | human | D-04 training-crawler decision (asked this session) | approved-with-qualifier (search bots; training bots pending D-04) | robots.txt |
| C-21 | downloads.json: 4 platforms listed, all `artifacts: []`, no per-platform status field | machine | downloads.json:9-38; F-07 | campaign 2026-10-28 | human (manifest owner — B-06, asked this session) | manifest contract decision; first artifact published | pending-evidence | downloads.json |
| C-22 | FAQPage JSON-LD parity with visible FAQ (20/20 questions AND answers byte-equal) | machine | index.html:40-207 vs 842-921; crawl-report.json faq_parity (via RECON §5) | campaign 2026-10-28 (via RECON) | campaign | any FAQ edit (re-run audit_site.py) | approved-with-qualifier (zero rich-result expectation, D-03) | / |
| C-23 | SoftwareApplication JSON-LD (name, description, category, OS, license, featureList x6) matches visible content | machine | index.html:18-39; parity via RECON §5 | campaign 2026-10-28 (via RECON) | campaign | any schema or visible-copy change (re-run audit_site.py) | approved | / |
| C-24 | JSON-LD `dateModified: 2026-10-26` | machine | index.html:37 (manual field; matched file mtime at audit, RECON §3) | campaign 2026-10-28 (via RECON) | campaign | ANY visible-copy change must update this field (no render path exists — hand-updated; this row is the refresh trigger) | pending-evidence (process, not fact) | / |
| C-25 | "Bubblewrap isolation … is not a virtual machine … do not guarantee safe decisions" | security | FAQ index.html:919-920; llms.txt draft keeps | campaign 2026-10-28 | campaign | sandbox mechanism change | approved (qualifier MANDATORY; anchor for all security wording) | / |
| C-26 | Evidence ledger: what works / experimental / unavailable is documented in the repo | capability | docs/realignment/ledger.md + docs/realignment/baseline.md exist (ls verified 2026-10-28); llms.txt:17; README:16-18 | campaign 2026-10-28 | campaign | ledger retired or moved | approved | llms.txt, README |

## Prohibited / removed claims (enforces RESEARCH §8; campaign-wide, no expiry)
| Claim | Reason | Replacement wording | Date |
|---|---|---|---|
| "Secure / safe / unhackable" | No security audit on record; own FAQ says "not a VM", no guarantees (index.html:920) | "Ask-first approvals, optional Linux sandbox, and honest limits — see the safety model" | 2026-10-28 |
| "Better than OpenClaw / Open WebUI" | Comparative claims need current verified facts on both sides | Factual contrast per C-09 wording | 2026-10-28 |
| "Free forever" / "no costs" | Provider billing exists (FAQ index.html:848) | "The software is MIT-licensed and free; model usage is billed by your provider" (C-10) | 2026-10-28 |
| "Works on macOS / Windows" | Not implemented (index.html:811) | "Linux today; macOS/Windows on the roadmap" | 2026-10-28 |
| "Private / nothing leaves your machine" (unqualified) | Hosted routes send prompts (FAQ index.html:872) | C-07 wording with qualifier | 2026-10-28 |
| "Production-ready" / "enterprise" | Development preview (README:16-22) | "Development preview; source-checkout install" (C-05, C-11) | 2026-10-28 |
| Any benchmark / "fastest" / timing or cost comparison | None run under test | Nothing until a reproducible benchmark exists | 2026-10-28 |
| Testimonials, user counts, star counts | None exist for Hutch | None | 2026-10-28 |
| "llms.txt improves your AI visibility" | Google ignores it for Search (RESEARCH §2A3) | "a summary file for agent tools" | 2026-10-28 |
| AI-Overview / ChatGPT citation guarantees | Engines non-deterministic; zero baseline | Dated observations only (D-07) | 2026-10-28 |
| "Private preview" as a stage term | Stale vocabulary that produced F-01; stage is "development preview" with PUBLIC source | C-05 wording | 2026-10-28 |

## Volatile facts index
| Fact | Source of truth | Render path | Refresh trigger | Current value |
|---|---|---|---|---|
| Version | pyproject.toml:3 (HEAD) | index.html:26 + :955 (hand-typed, 2 places — known duplication risk) | any release | 0.1.0 (no release tag; README:16-18) |
| dateModified | last site content change | index.html:37 (hand-typed) | any visible-copy change | 2026-10-28 (refreshed by slice S-b, 2026-10-28) |
| Platform availability | product reality | index.html:793-812 table (hand-maintained) | executor/platform change | Linux only |
| Model-route list | runtime config reality | index.html:32, llms.txt:5, README:10-13 (3 hand-typed places) | route add/remove | 8 routes |
| Image-input limits | product config | index.html:798, 863-864; llms.txt:15 (3 places) | limit change | 4 images / 1.5 MB |
| Competitor facts (C-09) | competitor self-description + incident record | FAQ index.html:852 | QUARTERLY re-verify (RESEARCH §1 sources) | as of 2026-10-28 |
| FAQ schema parity | visible FAQ | index.html:40-207 | any FAQ edit → re-run audit_site.py | 20/20 exact |
| Platform manifest | ? (B-06 owner) | downloads.json | manifest decision | 4 platforms, 0 artifacts |

## F-01 draft replacement wording — llms.txt (APPLIED verbatim in slice S-a, 2026-10-28; kept for the record)
- llms.txt:3 before: "…assistants ask for your approval before important actions. It is a private preview: there is no public download yet."
- llms.txt:3 after: "…assistants ask for your approval before important actions. The source is public and MIT-licensed on GitHub; there are no packaged desktop installers."
- llms.txt:9 before: "- Status: private preview. Source and downloads are not public, and there is no hosted sign-up."
- llms.txt:9 after: "- Status: development preview. The MIT-licensed source is public on GitHub; there are no packaged desktop installers and no hosted sign-up."
- F-06 addition (new line after the Key facts heading or as final line, e.g. replace llms.txt:25 tail): "- Repository: https://github.com/K-Arthur/hutch — the README and the repository's evidence ledger are the canonical summary of current capabilities."
- Consistency check for S-a: after edit, no occurrence of "private preview" may remain in llms.txt; every fact must match README:5,16-22 and index.html:793,780 (C-05, C-11, C-12); audit_site.py must pass.

## Review log
| Date | Change | Approver | Notes |
|---|---|---|---|
| 2026-10-28 | Register drafted (C-01..C-26, prohibitions, volatile index, F-01 wording) | campaign | Covers RECON §6 inventory + JSON-LD fields per session-3 brief |
| 2026-10-28 | Human sign-off on register + F-01 wording | human owner (question tool) | APPROVED; D-01=Option A, D-04=allow-all, B-06=desktop pipeline owns manifest (DECISION.md P2-01..P2-05). S-a unblocked. |
| 2026-10-28 | Slice S-a applied the approved F-01 wording verbatim; C-15/C-16/C-17 flipped to resolved | campaign (no wording changed vs approved draft) | Evidence: EVIDENCE.md AC table; audit crawl s-a-crawl-stdout.txt; commit `seo(slice-s-a): …`. Scope note: this status flip extends the session's minimum write list — it is the rows' own registered refresh trigger (DECISION.md S-a-01). |
| 2026-10-28 | Slice S-b: C-24 refresh trigger fired (head description :7 + new hero trust line :281 are visible copy) — dateModified 2026-10-26→2026-10-28; C-02/C-03 gain a hero placement (index.html:281, P2-01 approved wording verbatim); description facts re-verified against C-01/C-02/C-03/C-05/C-06 | campaign (human approved Route A via question tool same day) | Evidence: EVIDENCE.md AC1-7; crawl s-b-audit-stdout.txt (description_len=157, FAQ 20/20); commit `seo(slice-s-b): …`. No new claim rows needed — the trust string is the register's own approved wording. |
