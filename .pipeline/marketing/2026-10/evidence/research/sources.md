# Research source log — Hutch campaign — fetched 2026-10-28

All entries fetched this session via websearch/webfetch unless marked `[repo]` or `[secondary]`.
Quotes ≤40 words; full pages available at URLs (websearch results are session snapshots — re-verify before quoting in public copy).

| # | Source | URL | Published/updated | Type | Note |
|---|---|---|---|---|---|
| 1 | Google AI features and your website | https://developers.google.com/search/docs/appearance/ai-features | 2025-12-10 (page stamp) | primary | No extra requirements for AI Overviews/AI Mode; must be indexed + snippet-eligible; structured data must match visible text |
| 2 | Google AI optimization guide | https://developers.google.com/search/docs/fundamentals/ai-optimization-guide | 2026 | primary | "LLMS.txt files and other 'special' markup… Google Search itself doesn't use them"; no chunking/AI-rewrites/inauthentic mentions needed |
| 3 | Google Search documentation updates (changelog) | https://developers.google.com/search/updates | 2026 entries | primary | FAQ rich result deprecated (May 7, 2026) + docs removed (Jun 15, 2026); llms.txt clarification (Jun 15, 2026); spam policies apply to generative AI responses |
| 4 | Google spam policies | https://developers.google.com/search/docs/essentials/spam-policies | current | primary | Scaled content abuse "no matter how it's created"; site reputation abuse; expired domain abuse |
| 5 | Google common crawlers | https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers | current | primary | Google-Extended = Gemini training/grounding control; no Search ranking effect |
| 6 | Search Console: Search generative AI control | https://support.google.com/webmasters/answer/16908024 | rolled out worldwide 2026-08-31 | primary | Include/exclude control for AI Overviews/AI Mode/Discover gen-AI; Generative AI performance report |
| 7 | Google 2023 FAQ/HowTo changes (context) | https://developers.google.com/search/blog/2023/08/howto-faq-changes | 2023-08-08 (+09-14 upd) | primary | Historical restriction of FAQ rich results to gov/health |
| 8 | OpenAI crawlers | https://developers.openai.com/api/docs/bots | current | primary | OAI-SearchBot (search; opt-out = not shown in ChatGPT search answers), GPTBot (training), ChatGPT-User (user-triggered, robots.txt may not apply), OAI-AdsBot |
| 9 | Anthropic crawler docs | https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler | updated 2026-04-07 | primary | ClaudeBot (training), Claude-User (user fetches), Claude-SearchBot (search index); per-bot robots.txt |
| 10 | Perplexity crawlers | https://docs.perplexity.ai/docs/resources/perplexity-crawlers | current | primary | PerplexityBot (index, not training), Perplexity-User (user fetches, "generally ignores robots.txt"); published IP JSON |
| 11 | Cloudflare on Perplexity stealth crawling | https://blog.cloudflare.com/perplexity-is-using-stealth-undeclared-crawlers-to-evade-website-no-crawl-directives/ | 2025-08-04 | primary (accusation) | Contested; recorded as disagreement |
| 12 | Bing Webmaster Guidelines | https://www2.bing.com/webmasters/help/Webmaster-Guidelines-30fba23a | current | primary | IndexNow, XML sitemaps, NOARCHIVE/NOCACHE effects on Copilot grounding |
| 13 | Bing: AI Performance dashboard | https://blogs.bing.com/webmaster/2026/2/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview/ | 2026-02-10 | primary | First-party AI citation counts + grounding queries |
| 14 | Pew: AI Overviews click behavior | https://www.pewresearch.org/short-reads/2025/07/22/google-users-are-less-likely-to-click-on-links-when-an-ai-summary-appears-in-the-results/ | 2025-07-22 | primary (study) | 8% vs 15% click rates; 1% source clicks; 26% vs 16% session end; Wikipedia/YouTube/Reddit dominate citations |
| 15 | GEO: Generative Engine Optimization | https://arxiv.org/abs/2311.09735 | KDD 2024 (v3 2024-06-28) | primary (paper) | Citations/quotations/statistics up to +40% visibility; keyword stuffing ineffective; Perplexity test +37% |
| 16 | Core Web Vitals thresholds | https://web.dev/articles/defining-core-web-vitals-thresholds , https://web.dev/articles/vitals | current | primary | LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 @ p75 |
| 17 | OpenClaw repo + site | https://github.com/openclaw/openclaw , https://openclaw.ai/ | fetched current | primary | 393k stars, MIT, foundation, chat-channel positioning, desktop apps |
| 18 | CVE-2026-25253 | https://github.com/advisories/GHSA-g8p2-7wf7-98mq | 2026-01-31 | primary (advisory) | 1-click RCE via gatewayUrl token exfiltration; patched 2026.1.29 |
| 19 | ClawHub malware campaign | https://cantpwn.com/posts/skill-issues (PDF) ; https://www.esecurityplanet.com/threats/hundreds-of-malicious-skills-found-in-openclaws-clawhub/ | 2026-02-02 / 2026-02-03 | researcher + press | 341–386 malicious skills; AMOS stealers |
| 20 | cline npm supply-chain incident | https://www.stepsecurity.io/blog/cline-supply-chain-attack-detected-cline-2-3-0-silently-installs-openclaw ; https://osv.dev/vulnerability/GHSA-9ppg-jx86-fqw7 | 2026-02-17/19 | primary (advisory) | openclaw used as payload; ~4k downloads in ~8h |
| 21 | Open WebUI relicensing debate | https://www.reddit.com/r/LocalLLaMA/comments/1oy053m/ ; https://javisreview.com/review/open-webui-review-2026/ | 2025-11-15 / 2026-09-27 | community + secondary | Non-OSI licence with branding clause; controversy |
| 22 | Open WebUI model-switch leak concern | https://github.com/open-webui/open-webui/discussions/25012 | 2026-05-22 | community (primary doc of concern) | Mid-chat model switch can replay local-only history to cloud backends |
| 23 | Open WebUI RAG regression report | https://github.com/open-webui/open-webui/discussions/11388 | 2025-03-07 | community | Version regression complaints |
| 24 | GitHub Topics: openclaw ecosystem | https://github.com/topics/openclaw | fetched current | primary (directory) | nanobot, CowAgent, nanoclaw, zeroclaw, AionUi — light evidence |
| 25 | Lighthouse agentic browsing / llms.txt audit | via https://www.searchenginejournal.com/googles-llms-txt-guidance-depends-on-which-product-you-ask/575431/ ; https://searchscore.io/research/lighthouse-agentic-browsing/ | 2026-05/08 | `[secondary]` | Lighthouse 13.3 optional llms.txt audit; two Google positions (Search vs Chrome agents) |
| 26 | Ahrefs llms.txt log study | via https://www.webfx.com/blog/ai/how-to-optimize-for-ai-search/ (2026-07-24) | 2026 | `[secondary — trace to Ahrefs before quoting]` | 97% of llms.txt files got no requests (May 2026); AI bots 1.1% of requests |
| 27 | Copilot/Bing citation mechanics | https://cituna.com/learn/how-to-get-cited-by-copilot (2026-10-09) | secondary synthesis of Microsoft docs | `[secondary]` | Copilot shortens prompt → Bing query; citation queries visible 24h |
| 28 | Anthropic llms.txt recommendation | via https://www.getpassionfruit.com/blog/should-i-create-an-llms-txt-file-google-s-s-2026-guidance-explained | 2026-05-20 | `[secondary — fetch Anthropic "Writing for Agents" directly before relying]` | Claims Anthropic recommends llms.txt for agent-facing content |
| R1 | Hutch README | [repo] README.md | fetched 2026-10-28 | product evidence | Status, platform, licence, features, safety limits |
| R2 | Hutch site | [repo] website/index.html | fetched 2026-10-28 | product evidence | Title/meta/JSON-LD/FAQ content |
| R3 | Hutch llms.txt | [repo] website/llms.txt | fetched 2026-10-28 | product evidence | Stale "private preview" claims (conflict with R1) |
| R4 | Hutch robots.txt | [repo] website/robots.txt | fetched 2026-10-28 | product evidence | "no public domain chosen"; Allow: / |

Searches rate-limited/omitted: Bing Copilot crawler doc page (covered via #12/#13/#27); FTC endorsement guides (site has no testimonials — revisit before adding any).
