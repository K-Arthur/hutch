# STRATEGY — Hutch — 2026-10-28 (session 3, Phase 2)

> Phase 2 deliverable. Ends in HUMAN sign-off (§9). No wording ships to website/ this session.
> Evidence roots: RECON.md (measured), FINDINGS.md (F-01..F-12), RESEARCH.md (§1 landscape, §7 memos, §8 forbidden claims).

## 1. Positioning

- Category: **Self-hosted / local-first AI assistant platform** (searcher language: "self-hosted AI assistant", "personal AI agent on my own machine"). Primary category; boundary: NOT a chat front-end (Open WebUI's category), NOT a chat-channel gateway (OpenClaw's category). The differentiating sub-category, from measured white space (RESEARCH §1): **governed-by-default execution** — approvals, spend ceilings, evidence ledgers.
- Primary audience: technical builders on Linux who want repeat AI work (scheduled briefings, file chores, coding handoffs) to run on hardware they control, with a model route they choose. Narrowest audience with a recurring job: they already run Ollama or hold a provider key and distrust cloud agents' permission models.
- Secondary audiences (≤2): (a) privacy/local-first advocates evaluating whether prompts and state stay under their control; (b) operators of repeat work who need spend limits and reviewable receipts (the "runaway agent" fear, RESEARCH §3B2).
- Problem / status quo cost: cloud agents act with vendor-side authority — the category's documented failures are runaway spend, allowlist bypass and silent trust-boundary crossings (OpenClaw CVE-2026-25253; Open WebUI model-switch leak — RESEARCH §1, §3B2, sources fetched 2026-10-28). The do-nothing alternative is a folder of scripts that never gained judgment.
- Promise (one sentence): Assistants that run on your own Linux computer, ask before important actions, and keep every run reviewable — so repeat AI work stays useful without giving up control.
- Proof (types the product actually has): public MIT source (index.html:793, README:5); a real labelled app capture, not a mockup (index.html:316-335, RECON §9); honest availability table with experimental items marked (index.html:793-812); evidence ledger of what works vs experimental (docs/realignment/ledger.md, referenced llms.txt:17); exact-limit statements in FAQ (index.html:912, 920).
- Differentiators (≤3, each with "so what" + why not copied):
  1. **Governed by default** — ask-first approvals, hard-denied shell classes, no bulk approval (index.html:31, JSON-LD featureList; llms.txt:13). So what: consequential actions pause for a human. Why not copied: OpenClaw's design premise is broad access; retrofitting governance would contradict its own positioning (RESEARCH §1).
  2. **Estimated spend ceilings with reservations** — warn/approve-pause/admission ceiling, with the honest qualifier that provider billing stays authoritative (index.html:912-916). So what: a runaway loop hits a wall you set. Why not copied: cloud platforms can only meter after the fact; Hutch gates before admission.
  3. **Evidence as brand** — an always-current ledger of what works, what is experimental, what is unavailable, mirrored on the site's availability table (index.html:793-812; docs/realignment/ledger.md). So what: evaluators can verify instead of trust. Why not copied: no competitor in the measured set publishes one (RESEARCH §1 white space).
- Non-fit (trust signal): people without a Linux computer today (macOS/Windows executors unavailable, index.html:811); people wanting packaged desktop installers or hosted sign-up (neither exists, index.html:780); people unwilling to configure a model route themselves (index.html:856); anyone needing production-grade guarantees (development preview, README:16-22).
- Alternatives: hosted cloud agents (OpenClaw and kin); self-hosted chat front-ends (Open WebUI); a local model's own CLI; do-nothing scripts. Factual contrast already on the site at index.html:851-852.
- Claim boundaries: everything in RESEARCH §8 — no security superlatives, no "better than X", no "free forever", no Mac/Windows support claims, no "nothing leaves your machine", no "production-ready", no benchmarks, no testimonials, no llms.txt-as-SEO claims, no AI-visibility guarantees.

### Category essentials vs product (honesty audit)
| Category expectation | Hutch status |
|---|---|
| Works on Mac/Windows | NO — Linux only (index.html:811). Stated, not hidden. |
| One-click install | NO — source checkout (README:19). |
| Free tier | Software MIT/free; model usage billed by your provider (FAQ index.html:847-848). |
| Works out of the box | Partially — needs a configured model route (index.html:822). |
| Security story | Approvals + optional bubblewrap; explicitly "not a VM", no guarantees (index.html:920). |
Missing essentials are disclosed on-page; the strategy must never paper over them.

### D-01 — H1/hero positioning options (human picks one; measured state = RECON §9, F-10, F-12)

| | Option A — Warm H1 kept, trust words lifted (RECOMMENDED) | Option B — Category H1 | Option C — Split line |
|---|---|---|---|
| Change | H1 stays "A little help with what's next." (index.html:278). Add "MIT-licensed · open source · Linux" as a hero trust row above the fold (fixes F-12). Category words stay where measured: eyebrow (277), title tag (6), first sentence of hero-sub (279). | H1 becomes the category phrase (e.g. "Local-first AI assistants that run on your machine." — matches title tag exactly). Warm line moves to a prominent kicker. | H1 stays warm; a bold category line sits directly under it (between H1 and hero-sub). |
| AEO/SEO effect | Category present in title + H1-adjacent text (Bing title/H1/description alignment lever, RESEARCH §2A2). Weakest H1-level entity signal of the three. | Strongest on-page entity signal: H1 = strongest heading signal, matches title tag verbatim. Best for precise-phrase AI inclusion. | Middle: H1 stays uninformative to parsers; category line is visible text both engines and people read. |
| Brand effect | Keeps the distinctive human warmth; trust words now visible pre-scroll. | Loses the warm voice at the most-read line; reads like every dev-tool site. | Redundancy risk with hero-sub sentence 1 (near-duplicate category phrasing ~2 lines apart). |
| Effort / risk | Smallest diff (one added row); low risk; still a rendered change → Phase 3 gate + visual validation apply. | Larger content+layout change; needs full front-end gate; brand-voice decision, not just SEO. | Medium diff; layout change; redundancy needs careful wording. |
| Measured support | F-12 observation (desktop-top.png): trust words absent above fold. | F-10: H1 carries no category terms. | F-10 + F-12 both addressed partially. |

Recommendation: **Option A** — the measured state already places category words in the title tag, eyebrow and first sentence of the sub; the highest-leverage missing element above the fold is the trust row (F-12), not an H1 rewrite. Option B is defensible if the human prioritizes entity signal over voice. Decision belongs to the human (question asked this session; recorded in DECISION.md).

## 2. Message hierarchy

- One-liner: Hutch is a local-first platform for personal AI assistants that run on your own Linux computer — you choose the models, and assistants ask before important actions.
- Primary value: repeat AI work that stays under your control (approvals, spend ceilings, local evidence).
- Pillars (outcome → mechanism → proof):
  1. Control before consequence → ask-first approvals, hard-denied shell classes, no bulk approval → index.html:31 (JSON-LD featureList), FAQ index.html:919-920, llms.txt:13.
  2. Spend you can explain → warning / approval-pause / estimated admission ceiling before the prompt, provider billing named as authoritative → FAQ index.html:911-912, README budgets.
  3. Everything reviewable → hash-verified transcripts, local document store with SHA-256 checks, an evidence ledger → index.html:34, FAQ index.html:867-868, docs/realignment/ledger.md.
- Objections (objection → honest response → where proven):
  1. "Is it safe?" → Approvals and optional Linux sandbox give operator control; bubblewrap is not a VM and no guarantees are made → FAQ index.html:919-920.
  2. "What does it cost?" → Software is MIT-free; hosted model routes bill your provider; estimates are not provider-enforced limits → FAQ index.html:847-848, 911-912.
  3. "Does my data leave the machine?" → Control state stays local; hosted models receive the prompts you send them; network tools contact their destinations → FAQ index.html:871-872, 812.
  4. "Can I use it today?" → Development preview on Linux via source checkout; no installers, no hosted sign-up → FAQ index.html:844, README:16-22, index.html:780.
  5. "Is it production-ready?" → No; it is a development preview and says so everywhere (footer badge index.html:954-955, meta description index.html:7).
- Trust signals (verifiable only): public MIT source on GitHub; real dated app capture; availability table marking each area Supported/Experimental/Unavailable; version badge 0.1.0 triangulated (JSON-LD index.html:26 = footer :955 = pyproject 3).
- Primary CTA: View source on GitHub (index.html:774). Secondary CTA: Check availability / read the support boundaries (index.html:282, 825).

## 3. Audience/intent/page map

The site is one route + machine files (RECON §3). Each row is an anchored section owning one intent; machine files are derived surfaces, never claim sources (D-02/D-05: source order README/docs → site FAQ → llms.txt).

| Audience | Question/job | Intent | Canonical page (anchor) | Answer shape | Next action | Claim IDs |
|---|---|---|---|---|---|---|
| Developer, first touch | "What is this and does it fit me?" | informational | / (#top hero) | definition | See the app (#proof) | C-01..C-05 |
| Developer, credibility | "Is this real software or a mockup?" | informational | / (#proof) | screenshot proof | Check availability (#get) | C-14 |
| Privacy advocate | "What leaves my machine?" | informational | / (#runs) | boundary statement | Read FAQ (#faq) | C-06, C-07 |
| Operator | "What does a runaway bot cost me?" | commercial | / (#faq runaway) | FAQ + limits | GitHub source | C-08 |
| Evaluator, comparison | "How is it different from Open WebUI / OpenClaw?" | commercial | / (#faq different) | factual contrast | GitHub source | C-09 |
| Buyer, transaction | "Can I get it? What does it cost?" | transactional | / (#get) | availability table | View source / Linux setup | C-10..C-13 |
| Agent/AI answer | "Summarize Hutch accurately" | answers | /llms.txt (derived) | key-facts list | cite GitHub README | C-15..C-19 (stale → S-a) |
| Engine/crawler | "What may you fetch?" | machine | /robots.txt | allow-all | — | C-20 |
| Release tooling | "Where are binaries?" | machine | /downloads.json | manifest | — | C-21 (needs B-06) |
| Researcher | "How do I report a vulnerability?" | troubleshooting | /security.txt — ABSENT (F-11) | — | — | deferred to domain |

- Answer openings (first paragraph per page): hero sub already answers "what is it" in sentence 1 (index.html:279) — keep as the retrieval opening; FAQ #1 "What is Hutch?" (index.html:843-844) is the canonical long answer and must stay the summary of record.
- Internal links: hero → #proof → #get; #get → GitHub (#quickstart) and back to #proof/#runs (index.html:825); FAQ → support boundaries (#runs); footer → source + notices (index.html:976-983). No orphans measured (RECON §3).
- Search/AI queries (real phrasings, subset of RESEARCH §5): "self-hosted AI assistant Linux", "open-source AI assistant that asks before running commands", "stop AI agent spending too much", "runs fully offline with Ollama", "MIT alternative to hosted AI assistants", "Hutch AI assistant", "OpenClaw vs Open WebUI".
- Entity facts (one version, everywhere): name Hutch; category local-first multi-bot AI assistant platform; platform Linux (Python 3.11+); licence MIT; price software free / provider-billed usage; stage development preview; version 0.1.0; repo https://github.com/K-Arthur/hutch. Source order: README/docs → site FAQ → llms.txt.

## 4. Answer openings (first paragraph per page)
| Page | Required opening answer |
|---|---|
| / hero | "Hutch is a local-first assistant platform that runs on your own computer…" (index.html:279 — already correct; do not dilute) |
| FAQ #1 | "Hutch is a local-first, MIT-licensed platform for personal AI assistants… runs on your own Linux computer, not in a vendor's cloud." (index.html:844 — already correct) |
| llms.txt (S-a draft) | Blockquote ending "…The source is public and MIT-licensed on GitHub; it is a development preview with no packaged desktop installers." (draft in CLAIM-REGISTER C-15/C-16) |
| README | "local-first, MIT-licensed multi-bot platform in development preview (early software, Linux first)" (README:5 — keep as off-site entity opening) |

## 5. Internal linking plan
| From | To | Anchor/context | Reason |
|---|---|---|---|
| hero CTAs | #proof, #get | "See the app" / "Check availability" (index.html:281-282) | conversion path measured above-fold (RECON §9) |
| #get terminal aside | #proof, #runs | index.html:825 | keeps evaluators inside decision content |
| #get CTAs | GitHub #quickstart | index.html:774-775, 824 | transaction action = source checkout (only real path) |
| footer | GitHub, THIRD_PARTY_NOTICES.txt | index.html:976-979 | trust + legal |
| llms.txt (S-a) | GitHub README | to be added (F-06) | AI-answer citation path to the entity surface |
No new internal links planned beyond S-a; sitemap/domain links are B-01-gated (slice S-d).

## 6. Terminology and voice
- Glossary: assistant (site) = bot (CLI) — reconciled in FAQ index.html:844; "development preview" (never "beta", never "private preview"); "source checkout" (never "build from source"); model route (provider/model); run (one execution), step (unit within a run); approvals; transcript; workspace. Platforms: Linux, macOS, Windows — capitalization as written. Products: Open WebUI, OpenClaw, Ollama, llama.cpp, LM Studio, OpenRouter, OpenCode.
- Words to avoid: secure/safe (unqualified), enterprise, production-ready, "AI-powered" filler, unleash/empower/revolutionize, free forever, private (unqualified — "local-first" and "stays on your machine" with the hosted-route qualifier instead), "private preview" (stale term — F-01 root cause).
- Surface tone constraints: site = plain, honest, human (measured voice: "A little help with what's next."); docs = precise; llms.txt = neutral key-facts; UI = concise labels (PRODUCT.md brand commitments).
- Localization readiness: English only today (A-05); keep strings free of idioms; hero warmth line must survive +30-40% expansion if ever localized.

## 7. Content plan
| Page/route | Role | Intent | Keep/rewrite/merge/new/remove | Claim IDs | Proof assets | I/E/C | Priority |
|---|---|---|---|---|---|---|---|
| / (hero) | definition | informational | keep + small rewrite if D-01 = B/C; trust row for F-12 | C-01..C-05 | desktop-top.png | E | P1 |
| / (#proof..#faq sections) | decision content | commercial | keep (no changes proposed) | C-06..C-14 | captures, availability table | I | P2 |
| /robots.txt | machine | machine | keep; finalize after D-04 answer | C-20 | RESEARCH §4 | E | P1 |
| /llms.txt | derived agent file | answers | REWRITE (S-a: F-01 + F-06) | C-15..C-19 | S-a draft in CLAIM-REGISTER | I | P0 |
| /downloads.json | release manifest | machine | keep; add per-platform status only after B-06 owner confirms | C-21 | F-07 | C | P1 |
| /THIRD_PARTY_NOTICES.txt | legal | trust | keep | — | file | I | P3 |
| README (GitHub) | off-site entity page | informational | keep as canonical source; no edits this campaign | all | — | I | P2 |
| /sitemap.xml, canonical, GSC | technical SEO | machine | NEW — B-01-gated (S-d, not before domain) | — | F-02/F-03/F-09 | C | blocked |
| og:image + social meta | social citation | — | NEW asset (S-c, domain-independent; og:url waits for domain) | — | F-04 | C | P2 |
| /security.txt | trust | — | NEW — domain-gated + needs human contact address (F-11) | — | SECURITY.md (repo) | C | blocked |
No new content pages (no blog, no comparison pages, no programmatic pages — D-06, anti-patterns). Repair only.

## 8. Non-goals / will not claim
Per RESEARCH §8 (enforced by CLAIM-REGISTER below): no security superlatives; no "better than" comparisons; no free-forever; no Mac/Windows support claims; no absolute privacy claims; no production-ready; no benchmarks; no testimonials/user counts; no llms.txt-as-SEO; no AI-citation guarantees. Plus campaign non-goals: no mention-chasing (D-06), no new pages without unique-value + earn-links plan, no traffic promises (D-07, Pew 1% source clicks).

## 9. Human sign-off — RECORDED 2026-10-28
- Approver: human owner, via question tool, 2026-10-28.
- (1) D-01: **Option A approved** (keep warm H1; trust words lifted above fold in slice S-b). Options B/C rejected; positioning sentence + differentiators + non-fit approved as written.
- (2) D-04: **Allow all crawlers including training bots** (status quo maintained; no robots.txt change needed at S-d for this reason).
- (3) B-06: **Desktop release pipeline owns downloads.json** — campaign files requests, never edits.
- Claim register (C-01..C-26, prohibitions, volatile index, F-01 wording): **approved** (CLAIM-REGISTER review log).
- Changes requested: none beyond the recorded answers. Gate to Phase 4/5: PASSED — next session may execute slice S-a.
