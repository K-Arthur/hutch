# RESEARCH — Hutch — 2026-10-28

## 0. Scope, questions, method, limitations

- Product: Hutch — local-first, MIT-licensed multi-bot AI assistant platform in development preview (Linux, source-checkout install). See `README.md:1-22` and `website/index.html`.
- Audiences in scope: developers/technical builders on Linux; privacy/local-first buyers; operators of repeat automated work.
- Decisions this research must inform (5–8):
  1. D-01 Positioning/category framing for the site and entity surfaces.
  2. D-02 Status and justification of `website/llms.txt`.
  3. D-03 Structured-data policy (site ships `SoftwareApplication` + `FAQPage` JSON-LD).
  4. D-04 AI-crawler allow/deny policy for robots.txt.
  5. D-05 Entity-fact consistency across site / llms.txt / README (a live conflict exists — see §6).
  6. D-06 Off-site/citation strategy (what to earn, what not to chase).
  7. D-07 Measurement approach (honest, engine-aware).
  8. D-08 Domain/sitemap prerequisite (site currently has no public domain — blocker).
- Target engines: Google AI Overviews/AI Mode, ChatGPT Search, Perplexity, Bing Copilot, Gemini, Claude web search.
- Method: websearch + webfetch of primary sources on 2026-10-28; product facts read from repo files (`website/index.html`, `website/llms.txt`, `website/robots.txt`, `README.md`). All sources fetched this session; full log in `evidence/research/sources.md`.
- Limitations:
  - **AI-answer baseline could not be executed**: this environment cannot run prompts against the target answer engines (no browser/account access), and `website/robots.txt:1-2` says the site has "no public domain chosen", so live citation sampling is likely impossible until a domain exists. A dated prompt set is defined in §5 for the first runnable session. Recorded as a blocker, not skipped.
  - Bing documentation was reached via Bing Webmaster help pages + blogs.bing.com (primary) — fetched.
  - Competitor rows for smaller projects are from one GitHub Topics fetch (light evidence, marked).

## 1. Category and competitor landscape

Category as searchers phrase it: "self-hosted AI assistant", "local AI chat UI", "personal AI agent", "open-source AI agent framework". Hutch sits between (a) personal assistant gateways and (b) governed automation platforms.

| Product | Positioning (self-stated) | Differentiator claimed | Pricing/licence | Platforms | Proof style | Notable complaints (fetched evidence) |
|---|---|---|---|---|---|---|
| OpenClaw (github.com/openclaw/openclaw) | "The AI that really does things. Any OS. Any Platform." Personal assistant in 29 chat channels | Chat-app reach, foundation stewardship, full system access | MIT; 501(c)(3); no paid tier; 393k stars; 1.5M weekly npm downloads | macOS, Windows, Linux, iOS/Android | Docs, foundation, big community | CVE-2026-25253 1-click RCE (GHSA, 2026-01-31); ClawHub malware campaign: 341–386 malicious skills incl. AMOS stealers (Koi/cantpwn, 2026-02); used as payload in cline npm supply-chain incident (2026-02-17) |
| Open WebUI (github.com/open-webui/open-webui) | "A home for AI" — self-hosted, extensible, offline-capable chat platform | Best Ollama frontend; breadth (RAG, voice, plugins); 152k+ stars | Free; moved from OSI licence to custom licence with branding clause (v0.6.6+) | Docker/pip/uv/K8s | Community, feature depth | Licence-change backlash (HN thread, LocalLLaMA thread 2025-11-15: "5 or so license changes… broken some record"); RAG quality regressions (Discussion #11388); mid-chat model switch can leak local-only context to cloud backends (Discussion #25012); issue triage neglect (r/OpenWebUI 2025-06-02) |
| nanobot (HKUDS) | "Ultra-lightweight, self-hosted personal AI agent framework" (Python, WebUI, MCP) | Lightweight, multi-agent | OSS (unverified details) | self-hosted | GitHub repo | not investigated — light evidence |
| CowAgent (zhayujie) | Open-source personal AI assistant & agent harness; one-line install | Multi-agent/multi-model/multi-channel; lightweight | OSS (unverified details) | self-hosted | GitHub repo | not investigated — light evidence |
| nanoclaw | "Lightweight alternative to OpenClaw that runs in containers for security" | Container isolation; Agents SDK base | OSS | self-hosted | GitHub repo | not investigated — light evidence |
| zeroclaw (zeroclaw-labs) | "Fast, small, fully autonomous AI personal assistant infrastructure" | Autonomy, small footprint | OSS | any OS | GitHub repo | not investigated — light evidence |

White space (from fetched evidence — no competitor in this set leads with these):
- **Governed-by-default execution**: ask-first approvals, hard-denied command classes, spend ceilings, hash-verified transcripts. OpenClaw's incidents and Open WebUI's model-switch leak are the exact failure classes Hutch claims to engineer against.
- **Stable licence**: OpenClaw MIT-but-new foundation dynamics; Open WebUI relicensing controversy. Hutch's MIT licence is boring and stable — a truthful trust signal.
- **Honesty as brand**: nobody in the set publishes an evidence ledger of what works/what is experimental. Hutch already has `docs/realignment/ledger.md`; packaging that as public proof is uncontested territory.
- What is **not** white space and should not be chased: chat-channel breadth (OpenClaw owns it), model-front-end breadth (Open WebUI owns it), star counts.

## 2. Track A — what works (current practice)

### A1 Search intent and page fit
- Google's own AI-features doc: "There are no additional requirements to appear in AI Overviews or AI Mode, nor other special optimizations necessary." (developers.google.com/search/docs/appearance/ai-features, last updated 2025-12-10, fetched 2026-10-28). Eligibility = indexed + snippet-eligible + policies met. AI features are the same ranking systems, plus query fan-out.
- Bing/Copilot: Copilot composes answers from Bing's index via short generated queries; "a page Bing has not indexed… cannot be one of Copilot's sources" (cituna.com synthesis of Microsoft docs — secondary; Bing Webmaster Guidelines primary, fetched). Microsoft's guidance: title, H1 and meta description should line up for precise-phrase inclusion.
- Query shape predicts AI summaries: longer, question-word queries trigger AI Overviews far more (Pew: 53% of ≥10-word queries vs 8% of 1–2-word queries; pewresearch.org 2025-07-22). Implication: answer question-shaped intents ("What is X", "X vs Y", "Can I run X on Y") in plain language on the page.

### A2 On-page and technical
- Core Web Vitals (web.dev, fetched 2026-10-28): LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 at 75th percentile. Static site + web fonts are the usual levers.
- Structured data: "there's no special schema.org markup you need to add… it's a good idea to continue using it as part of your overall SEO strategy" (Google AI optimization guide, fetched). Requirement: structured data must match visible content (ai-features page).
- Rich-result reality check: FAQ rich results **stopped appearing May 7, 2026**; docs removed June 15, 2026 (Google Search Documentation Updates changelog entries "Deprecating the FAQ rich result feature" / "Removing documentation for the FAQ rich result feature", fetched). HowTo deprecated since Sept 2023. `SoftwareApp` rich results remain an eligible feature (structured-data feature guide still published; site currently emits `SoftwareApplication`).
- Sitemap + robots with absolute URLs once a domain exists (site has none: `website/robots.txt:1-2`).
- Bing-specific: `NOARCHIVE` removes content from Copilot answers; `NOCACHE` reduces citation to URL/title/snippet (Bing Webmaster Guidelines, fetched). Do not add these to marketing pages.
- IndexNow: notify Bing of URL changes; Bing explicitly names it for keeping AI answers current (Bing Webmaster Guidelines + blogs.bing.com AI Performance post 2026-02-10, fetched).

### A3 AI answer engines (per engine; uncertainty recorded)
- **Google (AI Overviews/AI Mode)**: controlled by Googlebot robots.txt + preview controls (`nosnippet`/`noindex`); Google-Extended only governs Gemini training/grounding, "does not impact a site's inclusion in Google Search" (developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers, fetched). New: Search Console "Search generative AI control" (rolled out worldwide 2026-08-31, support.google.com/webmasters/answer/16908024) with a Generative AI performance report — default is include. **Google ignores llms.txt for Search** ("neither harm nor help… Google Search ignores them", AI optimization guide, fetched).
- **ChatGPT Search**: `OAI-SearchBot` builds what's cited; opted-out sites "will not be shown in ChatGPT search answers" though they may appear as navigational links; `GPTBot` = training; `ChatGPT-User` = user-triggered fetches (robots.txt may not apply). ~24h robots.txt propagation (developers.openai.com/api/docs/bots, fetched).
- **Claude**: three bots — `ClaudeBot` (training), `Claude-User` (user-directed fetches), `Claude-SearchBot` (search index). Blocking Claude-User "may reduce your site's visibility for user-directed web search" (support.claude.com article 8896518, updated 2026-04-07, fetched). Anthropic publishes IP ranges; respects robots.txt.
- **Perplexity**: `PerplexityBot` (index; "not used to crawl content for AI foundation models"), `Perplexity-User` (live fetches; "generally ignores robots.txt" because user-requested) (docs.perplexity.ai, fetched). Caveat for the record: Cloudflare reported stealth-crawling by Perplexity in Aug 2025 (blog.cloudflare.com, fetched) — contested, listed as disagreement, conservative path = rely on robots.txt + verified IPs, don't build strategy on blocking.
- **Copilot/Bing**: Bing index feeds Copilot; control via bingbot + NOARCHIVE/NOCACHE + IndexNow (Bing Webmaster Guidelines, fetched). Bing Webmaster Tools now has an AI Performance dashboard (citations, grounding queries) — a first-party citation measurement source (blogs.bing.com 2026-02-10, fetched).
- **Gemini**: no separate search crawler; Google Search systems + Google-Extended for training/grounding control (Google crawler docs, fetched).
- Citation-selection mechanics: best controlled evidence is the GEO study (KDD 2024): adding **citations, quotations and statistics** raised visibility up to 40% in their benchmark and ~37% on Perplexity; keyword stuffing did not help (arxiv 2311.09735, fetched). Correlational/causal limits: lab benchmark on 2023–24 engines; treat as "supported tactic, modest confidence, re-verify".
- llms.txt status: Google says not needed for Search (primary, above). Lighthouse 13.3 added an optional "Agentic Browsing" audit that checks llms.txt presence (secondary: SEJ/SearchScore, fetched 2026-10-28). Anthropic recommends llms.txt in its agent-writing guidance (secondary claim via passionfruit/contentful articles; not fetched from Anthropic directly — mark `[secondary]`). Log study: 97% of published llms.txt files got zero requests in May 2026; AI bots were 1.1% of requests (Ahrefs study cited by webfx/contentful — `[secondary, trace to Ahrefs before quoting]`). Verdict: keep as low-cost agent-navigation affordance, never as an SEO claim.

### A4 Conversion and trust (dev-tool/local-first buyers)
- Decision-stage facts buyers need, and which the site already answers well: licence, platform support, what leaves the machine, cost of a runaway agent, sandbox limits (`website/index.html` FAQ). This content pattern (explicit limits, no superlatives) matches Google's "helpful, reliable, people-first content" expectations and protects against overclaiming.
- Verifiable trust signals in this category: public MIT source, release provenance/checksums, real screenshots (site labels captures with dates and conditions — good), evidence ledger. Fake/unverifiable: testimonials, awards, star-count boasting, "most secure".
- Pew data implies referrals from AI answers will be small even when cited (1% of AI-Overview visits click a source). Conversion strategy must not depend on AI-referral volume; brand/navigational demand and GitHub are the realistic funnels.

### A5 Off-site / entity
- The most-cited sources in AI Overviews are Wikipedia, YouTube, Reddit (15% of AI-summary sources; Pew, fetched). A small project cannot buy these; it can be present where category discussion happens (GitHub topics, HN, r/LocalLLaMA-style forums) with accurate facts.
- Entity consistency requirement (Microsoft/Bing guidance, fetched): "Name your product and competitors consistently… same brand and model names on /pricing, /features and /compare". Mismatched facts across site/README/llms.txt are how AI answers end up wrong.
- Google: "seeking inauthentic 'mentions' across the web isn't as helpful as it might seem" (AI optimization guide) — mention-chasing is explicitly a dead end; genuine third-party corroboration only.
- Original assets that could legitimately earn citations (product has the data): the complaints ledger (`docs/research/complaints.md`), the realignment evidence ledger, a Linux compatibility/support matrix, honest benchmark methodology (only if actually run).

## 3. Track B — what fails and why

### B1 Enforcement and penalties (Google spam policies; fetched from developers.google.com/search/docs/essentials/spam-policies)
- **Scaled content abuse**: "many pages generated for the primary purpose of manipulating search rankings… no matter how it's created", explicitly including generative-AI mass pages. Gate: this campaign adds pages only with unique value; no programmatic pages.
- **Site reputation abuse** (updated Nov 2024): third-party content riding host ranking signals — less relevant now, but any future sponsored/guest content must be editorially integrated or separate.
- **Expired domain abuse / doorway pages / thin affiliate**: not current tactics; hard "never" for this campaign.
- Google clarified its spam policies "also apply to generative AI responses in Google Search" (Search documentation updates changelog, fetched) — spam risk is not confined to blue links.
- Structured-data spam (schema not matching visible content) violates structured-data policies; the ai-features page repeats the requirement.

### B2 Product/category failures and complaints
- OpenClaw, the category leader, absorbed: 1-click RCE via token exfiltration (CVE-2026-25253, CVSS 8.8, patched 2026-01-29); a skills marketplace malware wave (341–386 malicious skills, AMOS stealers, Feb 2026); use as a payload in the cline npm compromise. Pattern: **broad system access + unvetted third-party content = supply-chain risk on the user's own machine.**
- Open WebUI: post-community-contribution relicensing backlash; RAG regressions; a documented path where mid-chat model switching sends local-only history to a cloud provider (Discussion #25012). Pattern: **trust is lost through licence moves and silent trust-boundary crossings.**
- Hutch's own thesis documents the same failure classes it designs against (runaway spend, allowlist bypass, permission fatigue) with sources in `docs/research/complaints.md` (product evidence, fetched from README:33-39).
- Honest mapping — which complaints Hutch can answer with product truth: unvetted skills (Hutch: trusted-and-reviewed skills, `README.md:91`), silent provider fallback (README:92,96), runaway spend (budgets/reservations, README:116), unevidenced capabilities (ledger). Out of scope / must not claim: "more secure than X", "prevents prompt injection", anything not in the ledger.

### B3 Marketing/AEO failure modes
- FAQ rich-result dependency: Google killed the rich result (May 2026) — a site whose FAQ schema strategy was built on rich results is now holding dead weight. Hutch ships `FAQPage` JSON-LD (`website/index.html:40-207`): markup is harmless and matches visible FAQ content, but must never be described as earning rich results.
- llms.txt cargo cult: Google explicitly ignores it for Search; log data shows near-zero fetches. Failure mode is claiming llms.txt as an "AI SEO" tactic on the site or in strategy docs. Hutch's file should exist for agent navigation + accuracy, and be kept factually current (it currently is not — see §6 conflict).
- AI-written thin pages / fake expertise: prohibited by scaled-content policy and by this campaign's non-negotiables.
- Zero-click collapse: Pew — sessions end 26% vs 16% on AI-summary SERPs; source clicks from AI summaries ~1%. Failure mode: KPI frameworks that promise traffic from AI answers.
- Single-sample "we're cited in ChatGPT" anecdotes: non-deterministic engines; invalid as evidence (methodological consensus in fetched practitioner sources; conservative path = fixed prompt set, multiple runs, dated).

### B4 Measurement traps
- Impressions up / clicks down (AI summaries absorb clicks): use Search Console's Web search type totals plus the Generative AI performance report separately; don't read aggregate CTR as content quality (Pew + Google docs).
- AI citation counts without referral: Bing's AI Performance dashboard counts citations, not value; report both citations and referred visits, and say plainly that referrals will be small (Pew).
- Branded-search inflation and rank trackers measuring a different SERP: out of scope for now; record so future sessions don't "prove" wins with them.

## 4. AI answer-engine mechanics (summary table)

| Engine | Retrieval path | Controlling signal | Citation lever | Uncertainty |
|---|---|---|---|---|
| Google AI Overviews/AI Mode | Googlebot index + query fan-out | robots.txt(Googlebot), Search generative AI control (default include) | classic SEO + question-shaped, snippet-worthy content | selection algorithm unpublished |
| ChatGPT Search | OAI-SearchBot index | robots.txt `OAI-SearchBot` | Bing-class fundamentals; fresh, quotable facts | retrieval internals unpublished |
| Perplexity | PerplexityBot index + live fetches | robots.txt + published IPs | citable tables/definitions | stealth-crawl dispute (Cloudflare 2025) |
| Copilot | Bing index | bingbot, IndexNow, NOARCHIVE/NOCACHE | Bing ranking for short phrases; title/H1/description alignment | query-shortening details partial |
| Gemini | Google Search systems | Googlebot + Google-Extended (training/grounding) | same as Google | overlap with AI Overviews unclear |
| Claude web search | Claude-SearchBot index + Claude-User fetches | robots.txt per-bot | accurate, quotable content; llms.txt per Anthropic guidance | Anthropic llms.txt recommendation `[secondary]` |

## 5. AI-answer baseline (prompt set + blocker)

- Blocker (documented): no answer-engine access from this environment; site has no public domain (`website/robots.txt:1-2`), so live sampling would likely return "product unknown" regardless.
- Prompt set v1 (run ≥2 prompts per engine on separate days; record engine mode, locale, date, screenshot; single samples are anecdotes):
  1. What is a local-first AI assistant platform?
  2. Best self-hosted AI assistant for Linux?
  3. OpenClaw vs Open WebUI — differences?
  4. Are there open-source AI assistants that ask before running commands?
  5. How do I stop an AI agent from spending too much on API calls?
  6. What AI assistants run fully offline with Ollama?
  7. Is there an MIT-licensed alternative to hosted AI assistants?
  8. What is Hutch AI assistant? (navigational)
  9. Hutch vs OpenClaw (comparison)
  10. Can I run AI assistants on my own computer without sending data to the cloud?
  11. What's the safest open-source AI agent framework?
  12. Do local AI agents support scheduled tasks?
  13. Which AI assistant tools have had security incidents?
  14. Best tools for personal AI automation 2026?
  15. Is Open WebUI safe? (adjacent complaint intent)
  16. How much does a self-hosted AI assistant cost?
- Per-prompt record: answer summary, cited URLs, product mentioned?, factual errors, date/locale/mode, screenshot path.

## 6. Entity facts sheet

| Fact | Canonical value | Sources | Surfaces where it appears | Mismatches |
|---|---|---|---|---|
| Name | Hutch | README:1, site title | site, README, llms.txt | none |
| Category | Local-first, multi-bot AI assistant platform | README:5, site FAQ | site, README, llms.txt | "bots" (CLI) vs "assistants" (site) — reconciled in site FAQ:50 |
| Licence | MIT | README:226, LICENSE | site JSON-LD, README, llms.txt | none |
| Platform | Linux only (Python 3.11+); macOS/Windows not implemented | README:20,217; llms.txt:10 | site FAQ, README, llms.txt | none |
| Price | Software free; hosted model usage billed by your own provider | site FAQ:58; llms.txt:11 | site, llms.txt | none |
| Stage | Development preview; no PyPI release; no public desktop download; source-checkout install | README:16-22 | site meta/FAQ, README | **CONFLICT**: llms.txt:3,9 says "private preview: source and downloads are not public" — contradicts README/site ("public MIT-licensed source"). llms.txt is stale. |
| Safety posture | Ask-first approvals, hard-denied shell classes, bubblewrap optional, "not a VM", no guarantees | site FAQ:202, README:117 | site FAQ, README | none (honest limits stated) |
| Version | softwareVersion 0.1.0 (site JSON-LD) | index.html:26 | site only | verify against releases in Phase 1 |

## 7. Decision memos

### D-01 Positioning
- Recommendation: Lead with **"governed local-first AI assistants"** — control, approvals, budgets, evidence — as the honest difference from OpenClaw (maximal access) and Open WebUI (chat front-end). Keep the human-tone hero; put category words ("local-first AI assistant platform", "runs on your own Linux computer", "open source, MIT") in title/H1-adjacent text and entity surfaces.
- Evidence: competitor positioning + incident record (§1, §3B2); Google AI-features doc (no special tricks — fundamentals + clear content); GEO paper (clear definitions/quotable facts help).
- Confidence: medium-high on substance; medium on SERP demand (unvalidated keyword volumes).
- Falsifier: AI-answer baseline showing engines already describe Hutch accurately and consistently without changes.

### D-02 llms.txt
- Recommendation: Keep the file (cheap, agent-navigation affordance, Anthropic-adjacent practice), but (a) fix its stale "private preview / source not public" facts, (b) never cite it as an SEO tactic, (c) keep it a faithful summary of visible site facts.
- Evidence: Google AI optimization guide (ignored by Search, fetched); Lighthouse agentic audit (secondary); Ahrefs log study (secondary); llms.txt:3,9 conflict (repo).
- Confidence: high on "not an SEO tactic"; medium on any upside.
- Falsifier: fetch logs later showing bots never read it and no agent referrals — then demote to minimal file.

### D-03 Structured data
- Recommendation: Keep `SoftwareApplication` (eligible feature; must match visible content — verify every field in Phase 1). Keep `FAQPage` only while the FAQ section exists visibly, with zero rich-result expectations; document deprecation in the claim register. No schema additions beyond these without an eligible feature.
- Evidence: Google changelog (FAQ rich results gone May 2026, fetched); structured-data feature guide still lists Software app; AI-features doc (schema must match visible text).
- Confidence: high.
- Falsifier: Google retiring the SoftwareApplication rich result — re-check changelog quarterly.

### D-04 AI crawler policy
- Recommendation: robots.txt default `Allow: /` for all search/user-fetch bots (Googlebot, Bingbot, OAI-SearchBot, ChatGPT-User, PerplexityBot, Perplexity-User, ClaudeBot, Claude-User, Claude-SearchBot). Training-data bots (GPTBot, ClaudeBot, Google-Extended, CCBot) are a **human decision** — surface options, default to current allow-all, no stealth changes.
- Evidence: per-engine docs (§4). Blocking search bots removes the site from that engine's answers by design.
- Confidence: high for search/user bots; training bots = values call → human.
- Falsifier: owner policy decision to block training crawlers; or verified harmful crawl volume.

### D-05 Entity consistency
- Recommendation: Single source-of-truth order: repo README/docs → site FAQ (canonical public summary) → llms.txt (derived summary). Fix llms.txt staleness in the first slice; add a refresh trigger to the claim register.
- Evidence: llms.txt:3,9 vs README:16-22 conflict (fetched both); Microsoft naming-consistency guidance; Google structured-data-matches-visible-content rule.
- Confidence: high.
- Falsifier: none plausible; consistency is cheap and required.

### D-06 Off-site / citations
- Recommendation: Earn citations via (1) accurate GitHub presence (README is already the de facto entity page), (2) the honest support/limits table and evidence ledger published in citable form, (3) original data (complaints taxonomy, compatibility matrix) — only what's real. No mention-chasing, no fake reviews, no comparison pages until facts are frozen in the claim register.
- Evidence: Google AI optimization guide (inauthentic mentions don't help); Pew (Wikipedia/Reddit/YouTube dominate — presence where discussion happens); GEO paper (citations/stats/quotes help).
- Confidence: medium.
- Falsifier: baseline showing category discussion forums are inaccessible/unresponsive to honest participation.

### D-07 Measurement
- Recommendation: Week 0: Search Console + Bing Webmaster Tools verification, sitemap, IndexNow once a domain exists. Track: indexed pages, GSC Web + Generative AI performance report, Bing AI Performance citations, fixed prompt-set results (dated, ≥2 runs), referred visits. Report honestly that AI-answer referral volume will be small (Pew 1%).
- Evidence: Bing AI Performance dashboard (primary, fetched); GSC generative AI control docs (primary, fetched); Pew (fetched).
- Confidence: high on tooling; low on any traffic promise — none will be made.
- Falsifier: n/a (measurement choice, not a claim).

### D-08 Domain/sitemap prerequisite (BLOCKER for public SEO work)
- Recommendation: Confirm the public domain and deploy path with the human before any technical-SEO slice. robots.txt currently documents the absence (website/robots.txt:1-2). Everything canonical/sitemap/Search-Console/IndexNow depends on this.
- Evidence: robots.txt:1-2; no site deploy in .github/workflows (checked 2026-10-28).
- Confidence: high that it blocks; ask human next session.

## 8. Claims we must NOT make

| Claim | Why not | Evidence gap | Replacement wording |
|---|---|---|---|
| "Secure / safe / unhackable" | OpenClaw had a patched CVE; Hutch's own FAQ says isolation "is not a VM" and gives no guarantees (index.html:202) | no security audit on record | "Ask-first approvals, optional Linux sandbox, and honest limits — see the safety model" |
| "Better than OpenClaw/Open WebUI" | Comparative claim needs current, verified facts on both sides; risks stale facts and legal exposure | no head-to-head testing | "Different defaults: governed by default; here's what each does" (factual contrast, sourced) |
| "Free forever" / "no costs" | Hosted model routes bill via provider (site FAQ:58); future unknown | pricing policy can change | "The software is MIT-licensed and free; model usage is billed by your provider" |
| "Works on Mac/Windows" | Explicitly not implemented (README:20,217) | — | "Linux today; macOS/Windows on the roadmap" |
| "Private / nothing leaves your machine" | Hosted routes send prompts to providers (site FAQ:106) | — | "Control state stays local; hosted models receive the prompts you send them" |
| "Production-ready" / "enterprise" | Development preview; release gates open (README:16-22) | — | "Development preview; source-checkout install" |
| Any benchmark ("fastest", token timings, cost comparisons) | none run under test | no benchmark | nothing until a reproducible benchmark exists |
| Testimonials, user counts, star counts | none exist for Hutch; competitor star counts are theirs | — | none |
| "llms.txt improves your AI visibility" | Google says it ignores it; no evidence | — | "a summary file for agent tools" (if mentioned at all) |
| AI-Overview/ChatGPT citation guarantees | engines non-deterministic; zero baseline data | no baseline | none; report observations with dates |

## 9. Source log (claim | URL | published | fetched | quote/note | confidence)

Full log: `evidence/research/sources.md`. Decision-critical primary sources (all fetched 2026-10-28):
- Google AI features & your website — developers.google.com/search/docs/appearance/ai-features (updated 2025-12-10) — "There are no additional requirements to appear in AI Overviews or AI Mode" — high.
- Google AI optimization guide — developers.google.com/search/docs/fundamentals/ai-optimization-guide (2026) — llms.txt/chunking/mentions myths — high.
- Google Search documentation updates (changelog) — developers.google.com/search/updates — FAQ deprecation (May/June 2026), llms.txt clarification (June 2026), spam policies apply to generative AI — high.
- Google spam policies — developers.google.com/search/docs/essentials/spam-policies — scaled content abuse definition — high.
- Google crawler docs — developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers — Google-Extended scope — high.
- Search Console generative AI control — support.google.com/webmasters/answer/16908024 (worldwide 2026-08-31) — high.
- OpenAI crawlers — developers.openai.com/api/docs/bots — OAI-SearchBot/GPTBot/ChatGPT-User — high.
- Anthropic crawlers — support.claude.com/en/articles/8896518 (updated 2026-04-07) — ClaudeBot/Claude-User/Claude-SearchBot — high.
- Perplexity crawlers — docs.perplexity.ai/docs/resources/perplexity-crawlers — high (Cloudflare counter-report noted as disagreement).
- Bing Webmaster Guidelines — www2.bing.com/webmasters/help/Webmaster-Guidelines-30fba23a — IndexNow, NOARCHIVE/NOCACHE, grounding eligibility — high.
- Bing AI Performance dashboard — blogs.bing.com/webmaster/2026/2/ (2026-02-10) — first-party AI citation measurement — high.
- Pew AI Overviews click study — pewresearch.org/short-reads/2025/07/22/ (2025-07-22) — 8% vs 15% clicks; 1% source clicks — high.
- GEO paper — arxiv.org/abs/2311.09735 (KDD 2024) — citations/quotes/statistics +40% visibility; keyword stuffing ineffective — medium (2023–24 engines).
- Core Web Vitals — web.dev/articles/defining-core-web-vitals-thresholds + /vitals — high.
- OpenClaw repo/site — github.com/openclaw/openclaw, openclaw.ai — high for self-description.
- CVE-2026-25253 — github.com/advisories/GHSA-g8p2-7wf7-98mq (2026-01-31) — high.
- ClawHub malware — cantpwn.com/posts/skill-issues (2026-02-02), esecurityplanet.com (2026-02-03) — medium-high (researcher reports).
- Open WebUI licence/RAG/leak — reddit r/LocalLLaMA 2025-11-15; github discussions #11388, #25012 — medium (community sources).
- Lighthouse agentic browsing + Ahrefs llms.txt log study — via SEJ/webfx/SearchScore (2026) — medium `[secondary]`.

## 10. Open questions / blockers
1. **Public domain + deploy target** for website/ — ANSWERED (human, 2026-10-28): no live domain yet; site is pre-launch. D-08 stands: all live-URL technical SEO (sitemap, canonical, GSC, IndexNow) and the AI-answer baseline wait for a domain decision; repo-based consistency/entity work proceeds now. GitHub (github.com/K-Arthur/hutch) is currently the only public entity surface.
2. AI-answer baseline blocked (no engine access; likely no live site). Prompt set ready (§5).
3. Training-crawler policy (GPTBot/ClaudeBot/Google-Extended) — human values decision (D-04).
4. Is the GitHub repo publicly linked from the site? (site says "public MIT-licensed source"; no visible link in the fetched head/nav — Phase 1 check.)
5. Analytics/Search Console/Bing Webmaster access — confirm ownership with human (Phase 1).
6. `softwareVersion` 0.1.0 currency vs releases (Phase 1).
