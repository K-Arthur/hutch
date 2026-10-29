# Research: completion evidence for the 2026-10-29 realignment slice

Date: 2026-10-29. Author: research teammate (researcher). Status: evidence input for the completion slice; this file makes recommendations, it does not change product behavior.

## Method and evidence grades

Read first, and not repeated here: [AGENTS.md](../../AGENTS.md), [complaints.md](../research/complaints.md) (revalidated 2026-10-07; its per-line caveats still apply), [claims-audit.md](claims-audit.md) (2026-10-07) and [baseline.md](baseline.md) (2026-10-07, skimmed). Repo facts below are referenced to source files, not re-derived.

Online work: web_search plus direct web_fetch of issue pages, GitHub REST payloads, Hacker News Algolia results, and vendor documentation, on 2026-10-29. GitHub's unauthenticated API rate limit interrupted some body fetches; unread fields are marked. Search-result titles without a snippet were not treated as read content.

Evidence grades used inline:

- Grades: **[user report]** first-person issue/forum report (proves a failure, not prevalence); **[maintainer report]** the project's own investigation with reproduction; **[vendor doc]** product or design-system documentation; **[vendor claim]** marketing or competitor positioning; **[third-party analysis]** analyst, agency, research or competitor content with an editorial interest; **[repo observation]** read in this repository; **[inference]** my judgement, not sourced to one page.

Prior evidence is not duplicated: local-first and agent-product complaints already catalogued in [complaints.md](../research/complaints.md), overclaims already corrected in [claims-audit.md](claims-audit.md), and what Hutch actually does in [baseline.md](baseline.md). This document adds newer primary reports, cross-product failure classes, and design practice.

## 1. Local-first AI assistants: what breaks and what earns trust

### Evidence

- **Interrupted model download corrupts the local cache.** Ollama issue [#19337](https://github.com/ollama/ollama/issues/19337) (opened 2026-10-27, open) reports that restarting the server more than an hour into a pull either fails forever on a missing `-partial-0` file or reports 100% of a too-small download and then fails digest verification. Recovery requires deleting files by hand. **[user report]** The report includes a cause analysis against `main`; it is one reporter, not a rate.
- **A hosted edge failure is indistinguishable from a model failure.** Ollama issue [#19111](https://github.com/ollama/ollama/issues/19111) (opened 2026-10-18, open) records `/v1/chat/completions` returning no HTTP response at all (curl code 000) while `/v1/models` answered in 1.07 s; queued requests then waited five minutes for a 429. **[user report]** The reporter says a whole Pro-plan workload became unusable on 2026-10-16.
- **Truncation can be reported as completion.** Ollama issue [#17272](https://github.com/ollama/ollama/issues/17272) (opened 2026-07-20, closed 2026-08-12) describes responses that "abruptly end" while behaving as if completed. **[user report]**
- **Driver/toolchain regressions read as product regressions.** LM Studio issue [#1048](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1048) (2025-10-01, closed 2025-10-08, 36 comments, label fixed-in-next-update) shows the Vulkan engine using 1/96 GB VRAM and CPU instead of GPU, with "x3 worse performance". **[user report]** One hardware configuration; the issue tracker's 2,014 open issues are a maintenance signal, not a rate.
- **Upgrades break previously working local models.** GPT4All issue [#3281](https://github.com/nomic-ai/gpt4all/issues/3281) (2024-12-13, closed same day) says none of 12 sideloaded models worked under Chat 3.5.1 after working in 3.4.2. **[user report]** GPT4All issue [#3635](https://github.com/nomic-ai/gpt4all/issues/3635) (opened 2025-11-23, open, unconfirmed) reports memory/CPU denial of service through unvalidated `max_tokens` and `n` on the local OpenAI-compatible server. **[user report]**
- **Settings and proxy paths are fragile in self-hosted setups.** LocalAI issue [#9125](https://github.com/mudler/LocalAI/issues/9125) (2026-03-24, closed 2026-08-03) reports watchdog settings not saving; issue [#9145](https://github.com/mudler/LocalAI/issues/9145) (2026-03-27, closed 2026-05-13) reports a reverse proxy under a sub-path breaking because absolute `/assets/` URLs were returned. **[user report]**
- **Hidden resource lifecycles lose work.** OpenCode issue [#48691](https://github.com/anomalyco/opencode/issues/48691) (2026-09-12, open, labels reproduced and severity:high) reports desktop terminals killed after 60 minutes without chat activity, with scrollback gone because location eviction does not know about terminals. Issue [#49719](https://github.com/anomalyco/opencode/issues/49719) (2026-09-18, open, reproduced) records a TUI crash on an event-stream disconnect. **[user report]**
- **Adoption is real.** On 2026-10-29 the GitHub API reported 185,194 stars for [ollama/ollama](https://github.com/ollama/ollama), 222,918 for [anomalyco/opencode](https://github.com/anomalyco/opencode), 77,352 for [nomic-ai/gpt4all](https://github.com/nomic-ai/gpt4all) and 50,046 for [mudler/LocalAI](https://github.com/mudler/LocalAI). **[repo observation]** Stars measure attention, not satisfaction.
- **The basic promise earns strong word of mouth.** A 2024-06-16 HN comment [40694480](https://news.ycombinator.com/item?id=40694480) says llama.cpp took ages to get on a GPU while Ollama "was setup and done in literally 3 minutes" and model load/unload management "just works". **[user report]** Positive counterweight to the failure list.

### Keep

- Say what is local, what leaves the machine, and what the provider bills; keep the existing "provider billing stays authoritative" caveat in [llms.txt](../../website/llms.txt).
- Show the configured route and readiness before work starts (the repo already tests first-run readiness states in [visual-validation.md](visual-validation.md)).
- Make upgrades explicit: compatibility notes before a model-format change, and a recovery path for an interrupted artifact rather than hand-deleting cache files.
- Label partial output: if the stream stops early, the run must not look complete.

### Avoid

- Reporting success when a local artifact is incomplete (the "100% of a too-small blob" class).
- Presenting a hosted-endpoint failure as a model-quality problem.
- Silent truncation, silent fallback, silent cache repair.
- Copy that implies "local" also means "no network": hosted routes and web tools still send data (already corrected in [claims-audit.md](claims-audit.md)).

## 2. Multi-bot orchestration UX failures and dashboard fatigue

### Evidence

- **Reopening a pane replays history as if it were current.** AgentMux maintainer report [REPORT_SWARM_SUBAGENT_HISTORY_FLOOD_2026_07_07](https://github.com/agentmuxai/agentmux/blob/08565342f171de40128c0d2cf67dc1d6c438c2a0/docs/specs/archive/REPORT_SWARM_SUBAGENT_HISTORY_FLOOD_2026_07_07.md) (2026-07-07): a pane reopened with an existing agent showed "a bunch of old subagents"; one session replayed 45 subagent-spawned events in under 500 ms. The user's words in the report: "we need an architecture rethink, this looks sloppy." **[maintainer report]**
- **Fabricated numbers next to real KPIs destroy trust.** The open-mercato [agent orchestrator UX audit](https://github.com/open-mercato/open-mercato/blob/ab23d45ffc3aeca5e7d994eb57d5526c5b0a4712/.ai/analysis/2026-07-12-agent-orchestrator-ux-audit.md) (2026-07-12, eight auditors, empty and populated passes with 43 screenshots) lists P0-5: "Where humans stepped in" shows hardcoded 412/188/96/61/53 interventions with no Sample label next to real KPIs. P0-6: a badge says "Action required: 110" while the primary inbox hard-caps at 20 with no pager. P1: window KPIs (p95, error rate) computed client-side from a single 100-row page, labeled as if aggregated. **[maintainer report]**
- **A fleet without a supervision surface becomes a human bottleneck.** A practitioner running 52 agentic jobs writes "I had no idea what half of them were doing": silent errors, jobs completing with partial data, an agent stuck in ERROR for weeks, and notifications as a wall of noise ([Sparkry, 2026-02-28](https://sparkryai.substack.com/p/i-run-55-ai-agents-i-had-no-idea)). **[user report]** Narrative, not measured.
- **Orchestrator-as-single-voice hides progress.** Ably argues that when parallel agents funnel through one orchestrator voice, users cannot see progress or intervene, and expect task state to reflect reality, including crashes ([Ably, 2026-01-29](https://ably.com/blog/multi-agent-ai-orchestrator-bottleneck)). **[third-party analysis]** Vendor content, but the failure mode matches the reports above.
- **Users lose track of which agent is doing what.** HN comment [49148020](https://news.ycombinator.com/item?id=49148020) (2026-08-02): "Trying to run too many agents, kept losing track of which are still going and what the status was." HN comment [48751858](https://news.ycombinator.com/item?id=48751858) (2026-07-01) describes juggling parallel CLI agents across machines; HN comment [43603049](https://news.ycombinator.com/item?id=43603049) (2025-04-06) says "so much time is wasted making dashboards that nobody cares enough to look at", echoed in [47498212](https://news.ycombinator.com/item?id=47498212) (2026-03-24). **[user reports]**
- **Multi-agent routing can spend money and discard output.** Swarms issue [#2044](https://github.com/kyegomez/swarms/issues/2044) (opened 2026-08-25, open, owner-authored) is titled "Only the first selected agent response is recorded; the rest are run, paid for, and discarded". **[maintainer report]**
- **Supervision is a research-level design problem, not a widget list.** OrchVis (arXiv [2510.24937](https://arxiv.org/abs/2510.24937), submitted 2025-10-28) builds hierarchical goal alignment, automated verification, an interactive planning panel, dependency visualization and selective replanning so a human can supervise without micromanaging every step. **[third-party analysis]** A design pattern source, not a product comparison.
- **A supervision kit is documented as a kit.** The agent-building playbook pattern [Supervise Many Agents Through One Interface](https://github.com/ramparte/agent-building-playbook/blob/ca2ab73f4837ff50d0577c09d1a55a9536072584/patterns/supervise-many-agents.md) names status exhaust, an attention firewall, an interrupt policy, a risk-ordered review queue, and a cost monitor, and warns not to build a fleet surface for one or two agents. **[third-party analysis]**

### Keep

- One exception-first triage: needs your action, then failed, then running, then done, then history; the repo's existing three-question triage is the right skeleton.
- Scope every list to the current session/bot/run and label historical items as history; do not rebuild "current" state by replaying durable history.
- Counts must state their denominator ("20 of 110") and sampled metrics must say "newest 100 of N".
- Per-bot single-run rule and a durable run registry are already the baseline; show them.
- Cost and step counters next to the work they describe, not only on a separate page.

### Avoid

- Dashboard-as-wall-of-widgets with no action queue.
- Reopening a pane and replaying old subagents/events as if live.
- Fabricated or demo numbers adjacent to real KPIs without a Sample label.
- A badge that counts more than the list can show.
- Duplicate event rendering (same run counted in two surfaces) or client-side joins presented as aggregates.
- Adding a fleet dashboard before the user has a fleet (playbook's own warning).

## 3. Empty states and loading skeletons

### Evidence

- Skeleton states are for initial full-page loads and should mimic the final layout; only container/data components get them, not buttons, inputs, toasts, modals or dropdown items. Animation conveys "not stuck" but can distract and create accessibility problems; a frame-only skeleton is effectively a spinner ([NN/g, Skeleton Screens 101, 2023-06-04, last reviewed 2026-09-02](https://www.nngroup.com/articles/skeleton-screens/)). **[third-party analysis]**
- Use a skeleton for waits under ~10 s, a spinner for 2-10 s, and a progress bar beyond that; blank space reads as broken ([same NN/g article](https://www.nngroup.com/articles/skeleton-screens/)). **[vendor doc]**
- Carbon's loading pattern (last updated 2026-08-11) adds progressive loading (structure first, images/lazy content later), inline loading for one component, "load more" for long lists, and an accessibility requirement that a screen reader be told about loading, busy, stuck and failed states ([Carbon Loading](https://www.carbondesignsystem.com/building-blocks/core/patterns/loading)). **[vendor doc]**
- Carbon's empty-state pattern distinguishes first-use, user-action and error empty states, with a positive title and a primary action ([Carbon Empty states](https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states), last updated 2026-08-11); NN/g's guidelines say blank unconfigured containers "create confusion and decrease user confidence" and that empty states are common during onboarding ([NN/g, 2021-09-19](https://www.nngroup.com/articles/empty-state-interface-design/)). **[third-party analysis]**
- Repo observation: dashboard loading is often a spinner inside the empty-state block, e.g. [skills.js](../../src/hutch/server/static/skills.js):104,126 ("Loading skills..." with a spinner) and [app.js](../../src/hutch/server/static/app.js):7264,7609 ("Loading schedules...", "Loading past work..."); no skeleton component was found by grep. Substantive empty-state copy does exist (for example the schedule and history empty states). **[repo observation]**
- The failure mode to avoid is already documented in this repo family of products: a dashboard that substitutes demo data for an error state, so "users may believe the displayed data reflects the real cluster state" ([kubestellar/console #2647](https://github.com/kubestellar/console/issues/2647), 2026-03-15, closed 2026-03-16). See section 6.5. **[user report]**

### Keep

- One polite status region (`role="status"` / `aria-live="polite"`) that announces loading, busy, failure and retry, without moving focus.
- Skeletons that match the final block sizes and text lines, for lists, cards and tables.
- A real empty state per surface: what this is, why it is empty, one primary next action (create assistant, add a schedule, configure a model route).
- Distinct empty, error, degraded and loading states; a Retry action on error.
- Test both empty and populated renders in Playwright, the way the open-mercato audit did.

### Avoid

- A blank screen or a bare spinner for a multi-second page load.
- A skeleton that never resolves: add a timeout that turns it into an error with Retry.
- Frame-only skeletons and shimmer that ignores `prefers-reduced-motion`.
- Reusing the empty state for errors without changing the wording or action.
- Demo/sample content silently filling a failed request (section 6.5).
- Success-toned toasts for no-op controls; the open-mercato audit found enabled "Take over" buttons that flash success and do nothing.

## 4. Playwright visual-regression testing in CI

### Evidence

- Playwright's own docs: rendering varies by OS, browser version, hardware, headless mode and power source, so baselines must be generated in the environment that runs the comparison. The snapshot filename embeds browser and platform (`...-chromium-linux.png` vs `...-chromium-darwin.png`), so a laptop-generated baseline is simply missing on Linux CI. Options include `threshold` (perceived colour difference, default 0.2), `maxDiffPixels`, `maxDiffPixelRatio`, `mask` for dynamic regions, `stylePath` for injected CSS, and `snapshotPathTemplate`. Animations are disabled and the caret hidden by default; the docs say to commit the snapshot directory and review changes ([Playwright, Visual comparisons](https://playwright.dev/docs/test-snapshots), accessed 2026-10-29). **[vendor doc]**
- The practical CI rule is one environment: the official Playwright Docker image pinned to the exact Playwright version (example `mcr.microsoft.com/playwright:v1.61.0-noble`), baselines updated inside that image or by a `workflow_dispatch` job that commits regenerated PNGs, and the HTML report uploaded on failure because it holds actual/expected/diff images ([Argos, 2026-08-18](https://argos-ci.com/blog/playwright-visual-regression-testing-ci)). **[third-party analysis]** Vendor guide; the mechanics match Playwright's docs.
- Threshold advice: start at zero tolerance, add `maxDiffPixels` only where a screenshot legitimately jitters; `maxDiffPixelRatio` scales with image size and can hide a real one-line regression inside a large full-page capture; masking dynamic elements is a better first fix than raising tolerance ([Argos, 2026-08-18](https://argos-ci.com/blog/playwright-visual-regression-testing-ci)). **[third-party analysis]**
- Flake sources are network latency (font/image not loaded), lazy loading, animations, and dynamic content such as dates. Fixes: wait for resources and network idle, wait for `[aria-busy]` loaders to be removed, inject CSS to hide volatile elements, keep a stable dataset ([Argos, 2024-02-15](https://argos-ci.com/blog/screenshot-stabilization)). **[third-party analysis]**
- Algorithm choice sets signal-to-noise: pixelmatch (Playwright's diff engine) processed a 1440x900 capture in ~28 ms versus ~85 ms for SSIM in this comparison; the same guide cites a 2025 ICST study of 94 open-source developers finding flakiness and long execution times the top obstacles to UI-test adoption, and a practitioner survey claim that ~40% of teams abandon visual testing because of maintenance burden ([Wopee, 2026-05-12](https://wopee.io/blog/screenshot-comparison-algorithms-visual-testing/)). **[third-party analysis]** Cite the study claims as the blog reports them, not as verified here.
- SSIM is not a default toggle: Playwright's built-in comparator is pixelmatch-based; an experimental `ssim-cie94` comparator was discussed in [microsoft/playwright #32057](https://github.com/microsoft/playwright/issues/32057), and a later commit warns not to use the `threshold` option with it ([commit cac67fb](https://github.com/microsoft/playwright/commit/cac67fb94f2c8a0ee82878054c39790e660f17ca)). **[maintainer report]**
- Repo observation: [pyproject.toml](../../pyproject.toml) declares `browser = ["playwright>=1.45"]`, an unpinned floor; the visual-validation record captures Playwright 1.63.0 and Chromium 153.0.8010.12 for local artifacts ([visual-validation.md](visual-validation.md)), and [tests/e2e/test_website.py](../../tests/e2e/test_website.py) is a browser/visual suite with asset-hash and metadata checks. **[repo observation]**

### Keep

- One pinned Playwright + browser version (and ideally the Docker image) for every baseline and every CI run; regenerate baselines only from that environment.
- Committed baselines per platform with a documented update path; review the diff images before merging.
- Masks for timestamps, charts, avatars, IDs, live counters; `stylePath` for known-variable regions; `prefers-reduced-motion` and animation disabling.
- Deterministic fixtures and a stable dataset; wait on explicit `aria-busy`/font readiness rather than fixed sleeps.
- Tolerance starts at zero; raise only with a comment naming the jittering pixels.
- Upload traces/reports/actual-diff images on failure; retry with a trace attached.

### Avoid

- Baselines generated on a laptop and compared on Linux CI.
- Unpinned browser/Playwright in CI.
- Blanket `maxDiffPixelRatio`/SSIM thresholds used to make a suite green.
- Screenshotting hover/focus state, caret, animations, or a live clock.
- Updating baselines in the same PR as a UI change with no human review.
- Threshold numbers copied from another project: the same percentage means different things at viewport and full-page sizes.

## 5. Marketing-site credibility and GitHub Pages SEO

### Evidence

- llms.txt v2 is a proposal to put a short, structured markdown index at the site root (or any path), with markdown twins of pages and `rel="alternate" type="text/markdown"` / `rel="describedby"` links; the author reports thousands of sites publishing one, documentation platforms generating them, and Lighthouse auditing sites for one, plus OpenAI, Anthropic and Gemini publishing llms.txt for their own developer docs ([llmstxt.org](https://llmstxt.org/), published 2024-09-03, modified 2026-08-10). **[vendor claim]** Adoption counts are the proposal author's claims.
- Vendor adoption is visible: the OpenAI API reference page itself says "For the complete documentation index, see llms.txt. Markdown versions of documentation pages are available by appending .md to the page URL" ([OpenAI API reference: Audit Logs](https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/audit_logs), accessed 2026-10-29). **[vendor doc]**
- Google documents canonical URLs as the way to consolidate duplicate URLs from different hosts or paths, and sitemaps as the discovery mechanism for URLs it might not otherwise find ([canonical](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls), [sitemaps](https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview), accessed 2026-10-29). **[vendor doc]**
- The Open Graph protocol requires four properties on every page: `og:title`, `og:type`, `og:image`, `og:url` (the canonical URL), with `og:description` recommended ([ogp.me](https://ogp.me/), accessed 2026-10-29). **[vendor doc]**
- An audit of a real GitHub Pages Jekyll site on 2026-10-29 found all 15 pages with meta descriptions Google would cut off, titles too long, no `og:image`, and no robots.txt, sitemap or llms.txt at the origin; the author wired the audit into CI with `--fail-under` and SARIF output ([rankprobe, dev.to, 2026-10-29](https://dev.to/bayuh85/rankprobe-an-seo-and-ai-crawler-audit-that-fails-your-pr-before-a-stray-noindex-ships-1h1g)). **[user report]**
- Developer audiences are skeptical; verifiable GitHub signals (stars, contributor growth, forks, release velocity) beat unverifiable "trusted by" language, and specific proof beats vague claims ([getstarted.page, 2026-04-17](https://getstarted.page/use-github-signals-to-build-credibility-for-developer-focuse)). **[third-party analysis]** Agency content with an interest in GitHub-signal marketing.
- Repo observation: the site is already strong on these signals. [website/index.html](../../website/index.html) has title, a description naming "development preview", canonical `https://k-arthur.github.io/hutch/`, matching `og:url`, OG/Twitter tags, a 1200x630 OG image with dimensions, two JSON-LD blocks (SoftwareApplication + FAQPage), theme-color and icons. [website/sitemap.xml](../../website/sitemap.xml) has one URL with `lastmod` 2026-10-28. [website/robots.txt](../../website/robots.txt) correctly notes that a project site cannot control the origin-root robots.txt and that all crawlers are allowed. [website/llms.txt](../../website/llms.txt) is 26 lines with "Key facts" and "Not claims". [website/security.txt](../../website/security.txt) exists with an expiry in 2027. [tests/e2e/test_website.py](../../tests/e2e/test_website.py) already asserts the description names local-first and development preview, `og:title` equals the page title, JSON-LD software fields, FAQ schema equal to the visible FAQ, and bans superlatives in FAQ answers. [marketing-site.md](../marketing-site.md) is the claim policy. **[repo observation]**
- Prior credibility failure class: [claims-audit.md](claims-audit.md) records dead install and GitHub links that returned 404 anonymously; that is the exact failure a dev-tool site cannot afford. **[repo observation]**

### Keep

- One canonical URL everywhere: `<link rel="canonical">`, `og:url`, sitemap `<loc>`, llms.txt site line, JSON-LD `url` must all agree, and must be switched together on a custom domain.
- Absolute OG/Twitter image URLs with width/height and alt text; JSON-LD that matches the visible page; sitemap `lastmod` that tracks real edits.
- llms.txt in the "what it is / key facts / not claims" shape, linking to the repository's evidence docs; robots policy stated honestly, including the origin-root limitation.
- Claims that map to evidence docs; "development preview" and "no public install exists" stated plainly; security.txt and SECURITY.md.
- A CI check for metadata drift (canonical, og:url, title/description length, sitemap URLs, llms.txt links), following the rankprobe pattern.

### Avoid

- Dead GitHub/PyPI/install links or a README claim that the site contradicts.
- Canonical/og:url mismatch between project URL and custom domain; relative `og:image`.
- Meta descriptions long enough to be truncated, and titles over ~65 characters.
- Sitemap entries that 404 or omit real pages; llms.txt that repeats marketing rather than facts.
- Relying on `/repo/robots.txt` for crawler policy: only the origin root is read (the repo's robots.txt already says this).
- Superlatives and "trusted by" language without a verifiable link.

## 6. Specific issue classes on comparable platforms

### 6.1 Login and OTP failures

- **[user report]** adcontextprotocol issue [#5435](https://github.com/adcontextprotocol/adcp/issues/5435) (2026-06-09, closed 2026-06-12, labels bug/P0/admin-tool) reports an org member locked out since the weekend because OTP/magic link emails stopped arriving; six related escalations are linked. The fix took three days.
- **[user report]** OpenAI community thread [Case 14206599](https://community.openai.com/t/case-14206599-email-otp-factor-vanished-from-mfa-screen-locked-out-of-paid-pro-account-no-support-response/1395376) (2026-09-07) reports the Email OTP factor disappearing from the MFA screen, only "Authenticator app" offered, no recovery code issued, no active session, and no support response for five days. The reporter says other accounts on the same device still show Email OTP, so it is account-specific.
- Keep: at least two independent recovery factors; a recovery-code step that cannot be skipped silently; a visible account-security state (which factors are enrolled); status/incident communication; a support path that does not depend on the broken channel.
- Avoid: single-method MFA, silent factor removal, recovery behind support-only queue, and login pages that cannot distinguish "wrong code" from "no code sent".

### 6.2 Unclear model-route configuration

- **[user report]** LiteLLM issue [#12383](https://github.com/BerriAI/litellm/issues/12383) is titled "Models with 'default' tag are routed to even when tag is provided": an explicit selection loses to an implicit default.
- **[maintainer report]** agentgateway PR [#2244](https://github.com/agentgateway/agentgateway/pull/2244) (closed) fixes UI code that "tries to map a concrete model like gemini/bar to a provider in the list which may be like gemini/*. But it did so incorrectly resulting in wonky behavior." PR [#630](https://github.com/agentgateway/agentgateway/pull/630) adds wildcard matching for model aliases; both are UI/definition-shape mismatches, not model failures.
- **[third-party analysis, competitor]** A router vendor read 100 OpenClaw issues mentioning OpenRouter and categorized them: broken fallback/failover ~20, model ID mangling ~15, auth/401 ~8, cost/billing opacity ~6, routing opacity ~5, feature parity ~10, rate-limit/key exhaustion ~4, catalog staleness ~5 ([ClawRouter comparison doc](https://github.com/blockrunai/clawrouter/blob/7dca21323fc66905f1e69fd57565755500e579af/docs/clawrouter-vs-openrouter-llm-routing-comparison.md), also cross-posted on dev.to). The counts are the competitor's own reading; representative issues are linked in its table.
- **[user report]** Representative primary issue: OpenClaw [#45663](https://github.com/openclaw/openclaw/issues/45663) "Provider returned error from OpenRouter does not trigger model failover", with a fix PR [#47170](https://github.com/openclaw/openclaw/pull/47170) that classifies the error as retryable.
- Keep: show the effective route and the resolution order in the UI; distinguish explicit route from default/auto; a "test this route" that names the resolved model without spending tokens; explicit, logged failover with the reason; stable model IDs and visible aliases.
- Avoid: implicit defaults overriding an explicit tag; silent fallback to a different model; rewriting model IDs; auto-routing that does not display the chosen model; errors that say "provider error" without the route and HTTP status.

### 6.3 Hidden spending caps and billing surprises

- **[vendor claim/admission]** Cursor's 2025-07-04 post [Clarifying our pricing](https://cursor.com/en-US/blog/june-2025-pricing) says the pricing changes "were not communicated clearly", refunds unexpected usage charges from the prior three weeks, admits "we were not clear that 'unlimited usage' was only for Auto", and moves to an explicit spend limit option. A rare public admission of a cap-communication failure.
- **[user report]** A secondhand allegation, unverified: A Korean Claude user was reported to have received invoices for $1,669,875.90 and then $16,627,739.70 on a free account with no payment method and zero API usage in the dashboard; the bank declined both attempts and Anthropic had not responded at publication ([The News, 2026-07-11](https://www.thenews.com.pk/latest/1408788-why-did-anthropic-charge-a-free-user-166-million-despite-zero-api-usage)). The claim is unverified; the transferable failure is a billing surface that can disagree with dashboard usage.
- Prior evidence already in the repo: opaque/shrinking allowances in [complaints.md](../research/complaints.md) section 1, and the "hard spending caps" correction in [claims-audit.md](claims-audit.md). Do not restate those claims beyond this pointer.
- Keep: show cap, used, reserved, remaining, unit, and reset time together before a run; make reservations atomic across shared connections; state that provider billing is authoritative; alert at thresholds; refund/correct visibly when a charge is wrong.
- Avoid: "unlimited" without the route/model scope; caps that do not cover shared connections; usage screens that can disagree with invoices without a reconciliation note.

### 6.4 Missing audit trails

- **[third-party analysis]** The [Audit Log Wall of Shame](https://audit-logs.tax/) catalogs vendors whose audit logs are tier-gated, incomplete or inconsistent: 1Password (mixed timestamps, inconsistent event language, missing object/vault names), GitHub (standard logs omit IPs, changes omit old values), GitLab (highest tier only for streaming, missing project and group settings), Salesforce (24-hour log delay), Notion and Hugging Face (no API collection for audit logs), LastPass (no TOTP-code access events). It is a community list, not a study, but the failure patterns are concrete.
- **[vendor doc]** OpenAI publishes an audit-log API reference page, demonstrating that a machine-readable admin audit surface is an expected product feature at platform scale ([OpenAI API reference: Audit Logs](https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/audit_logs), accessed 2026-10-29).
- **[repo observation]** Hutch already keeps event history and surfaces degraded audit writes: [engine.py](../../src/hutch/engine.py):986 tracks failed audit writes "shown, never silent", and [store.py](../../src/hutch/store.py):11255 says event history is retained as an audit trail. There is no read-only audit export/view in the dashboard that I found.
- Keep: UTC ISO-8601 timestamps; actor, action, target, before/after values, outcome; append-only event history retained after deletion/revocation; degraded audit writes visible in the run and UI; an export a person can read without a database browser.
- Avoid: enterprise-tier-only audit access, local-time timestamps, missing object names, logged changes without old/new values, delayed or dropped events.

### 6.5 "Demo data" confusion

- **[user report]** kubestellar/console [#2647](https://github.com/kubestellar/console/issues/2647) (2026-03-15, closed 2026-03-16): when live API requests fail, the dashboard injects demo data; "users may believe the displayed data reflects the real cluster state when it is actually generated demo data." [#3252](https://github.com/kubestellar/console/issues/3252) (2026-03-23, closed) reports demo mode not clearing cached real-cluster data, so demo and real data mix. [#4198](https://github.com/kubestellar/console/issues/4198) reports demo data shown with a local agent running. [#2399](https://github.com/kubestellar/console/issues/2399) reports a demo badge shown while cards display live data.
- **[maintainer report]** The open-mercato audit's P0-5 is the same class: fabricated intervention counts with no Sample label next to real KPIs.
- Keep: one persistent, unmissable mode indicator that is derived from the data source; empty, demo, mock, stale and live are mutually exclusive labels; clearing caches on mode switch; sample labels on every fabricated number.
- Avoid: demo fallback on error, badge that can disagree with the data, any surface where a user cannot tell whether a number is real.

### 6.6 Dashboard metrics that reset on deploy

- **[user report]** headroom issue [#2137](https://github.com/headroomlabs-ai/headroom/issues/2137) (2026-07-13, closed 2026-07-15): most `/dashboard` values are process-local in `PrometheusMetrics`, so a proxy restart resets request counts, cache statistics and timing aggregates even with a persistent workspace volume; `/stats-history` survives while `/stats` appears to reset, which the reporter calls "confusing in normal single-worker Docker upgrades/redeployments".
- **[user report]** A Stack Overflow question describes multiple daily deployments resetting Prometheus metrics and asks how to handle it ([Stack Overflow 66462559](https://stackoverflow.com/questions/66462559)).
- Keep: durable aggregates; label scope ("since 2026-10-29 09:00", "since process start", "lifetime"); a restart marker when a counter was recreated; totals that do not silently differ from the history view.
- Avoid: in-memory-only counters presented as lifetime totals; a reset with no marker; two surfaces disagreeing about the same metric.

### 6.7 Tenant-scoping leaks

- **[user report]** soleur issue [#6306](https://github.com/jikig-ai/soleur/issues/6306) (2026-07-10, closed same day, P1): a `SECURITY DEFINER` SQL function granted to `anon` and `authenticated` returned every tenant's stuck conversation ids and user ids, bypassing base-table RLS. It was found by the project's own authz/RLS fuzz harness, not by review.
- Hutch is local-first and single-owner today, but the dashboard already has paired sessions and revocation, and a future hosted/team mode inherits this class. Treat scoping as a property of every query, not of the outer middleware.
- Keep: explicit owner/tenant id in every query and RPC; default-deny; negative tests that call every read endpoint as the wrong owner; grants on functions reviewed like schema changes; fuzzing/RLS harnesses in CI; scoping stated in API responses.
- Avoid: relying on RLS alone while `SECURITY DEFINER` functions exist; "admin" endpoints that return all rows without an explicit operator context; tenant id taken from a cookie header only.

## Realistically fixable in this completion slice

The split is about verification, not ambition: the first list can be checked offline with the existing mock runtime, fixtures and a local browser; the second needs things this environment does not have.

### Small fixes verifiable in this repo now

1. Docs and marketing copy: keep the claim/evidence mapping in [marketing-site.md](../marketing-site.md) and [claims-audit.md](claims-audit.md) current; check every site claim links to an evidence doc; keep "development preview" and "no install exists" consistent across site, llms.txt, README and landing copy.
2. Static-site metadata checks in [tests/e2e/test_website.py](../../tests/e2e/test_website.py): add canonical == `og:url` == sitemap loc, sitemap URLs that map to real files, llms.txt links that resolve, meta description <= ~160 characters and title <= ~65, and absolute OG image URL.
3. Dashboard states: replace spinner-only page loads in [app.js](../../src/hutch/server/static/app.js) and [skills.js](../../src/hutch/server/static/skills.js) with layout-matching skeletons; assert one polite status region; add explicit empty vs error vs degraded copy and Retry; add "N of M" denominators where a list is capped; never let demo or sample content fill a failed fetch.
4. API validation, mock-testable: expose the effective model route and its resolution order; reject or warn on an unknown/ambiguous route before a run; return cap, used, reserved, remaining and reset time from the budget endpoint; surface `audit_degraded` in the run view; add request/response contract tests for each.
5. Playwright policy: pin the Playwright/browser version in CI (the repo currently declares `playwright>=1.45` in [pyproject.toml](../../pyproject.toml)), record the pinned image, commit baselines, mask volatile regions, and upload traces/reports on failure. A local Playwright run with no live provider is in scope.
6. Audit trail: add a read-only event/audit view or export over the existing event history; verify UTC timestamps, actor, target, outcome and degraded-write visibility with fixtures.

### Needs external accounts, hardware or live providers

- Live runs against Ollama, LM Studio, LocalAI, GPT4All, hosted providers and OpenCode/OpenRouter routes: model-route behavior, failover, model-ID fidelity, VRAM/driver matrix regressions.
- Provider billing verification (caps, reservations, invoice reconciliation) because provider billing is authoritative and no live account is configured here.
- Real login/OTP/MFA flows (SMTP delivery, factor enrollment, recovery) and any CAPTCHA/headed browser challenge.
- GitHub Pages deployment, custom-domain DNS/HTTPS, Search Console indexing and any claim about search ranking or LLM-answer citation.
- A Docker/CI runner for pinned-image screenshot comparison, any hosted visual-review service, and cloud browser/OS targets.
- Real multi-tenant or team deployment for scoping, fuzzing and leak tests; current state is single-owner local-first.
- Phone/desktop hardware for touch, viewport and native-host behavior (baseline already lists live phone checks as unverified).

## Sources

Repo sources (read 2026-10-29):

- [AGENTS.md](../../AGENTS.md), [docs/marketing-site.md](../marketing-site.md), [docs/realignment/visual-validation.md](visual-validation.md), [docs/realignment/baseline.md](baseline.md), [docs/realignment/claims-audit.md](claims-audit.md), [docs/research/complaints.md](../research/complaints.md).
- [website/index.html](../../website/index.html), [website/robots.txt](../../website/robots.txt), [website/sitemap.xml](../../website/sitemap.xml), [website/llms.txt](../../website/llms.txt), [website/security.txt](../../website/security.txt), [tests/e2e/test_website.py](../../tests/e2e/test_website.py), [pyproject.toml](../../pyproject.toml).

External sources (accessed 2026-10-29 unless dated):

1. Ollama issue #19337, pull resume broken - https://github.com/ollama/ollama/issues/19337 - 2026-10-27.
2. Ollama issue #19111, cloud completions return no response - https://github.com/ollama/ollama/issues/19111 - 2026-10-18.
3. Ollama issue #17272, responses cut short - https://github.com/ollama/ollama/issues/17272 - 2026-07-20 (closed 2026-08-12).
4. LM Studio issue #1048, Vulkan regression - https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1048 - 2025-10-01 (closed 2025-10-08).
5. GPT4All issue #3281, 3.5.1 breaks sideloaded models - https://github.com/nomic-ai/gpt4all/issues/3281 - 2024-12-13.
6. GPT4All issue #3635, local server resource consumption - https://github.com/nomic-ai/gpt4all/issues/3635 - 2025-11-23.
7. LocalAI issue #9125, settings do not save - https://github.com/mudler/LocalAI/issues/9125 - 2026-03-24.
8. LocalAI issue #9145, X-Forwarded-Prefix regression - https://github.com/mudler/LocalAI/issues/9145 - 2026-03-27.
9. OpenCode issue #48691, terminals killed after inactivity - https://github.com/anomalyco/opencode/issues/48691 - 2026-09-12.
10. OpenCode issue #49719, TUI event-stream crash - https://github.com/anomalyco/opencode/issues/49719 - 2026-09-18.
11. HN comments, all fetched 2026-10-29: HN comment, Ollama setup "just works" - https://news.ycombinator.com/item?id=40694480 - 2024-06-16. HN comment, too many agents, lose track of status - https://news.ycombinator.com/item?id=49148020 - 2026-08-02. HN comment, parallel agents across machines - https://news.ycombinator.com/item?id=48751858 - 2026-07-01. HN comment, dashboards nobody cares to look at - https://news.ycombinator.com/item?id=43603049 - 2025-04-06. HN comment, dashboard nobody looks at - https://news.ycombinator.com/item?id=47498212 - 2026-03-24.
12. AgentMux report, swarm view floods with stale subagents - https://github.com/agentmuxai/agentmux/blob/08565342f171de40128c0d2cf67dc1d6c438c2a0/docs/specs/archive/REPORT_SWARM_SUBAGENT_HISTORY_FLOOD_2026_07_07.md - 2026-07-07.
13. open-mercato agent orchestrator UX audit - https://github.com/open-mercato/open-mercato/blob/ab23d45ffc3aeca5e7d994eb57d5526c5b0a4712/.ai/analysis/2026-07-12-agent-orchestrator-ux-audit.md - 2026-07-12.
14. Sparkry, "I Run 55 AI Agents" - https://sparkryai.substack.com/p/i-run-55-ai-agents-i-had-no-idea - 2026-02-28.
15. Ably, "Why orchestrators become a bottleneck" - https://ably.com/blog/multi-agent-ai-orchestrator-bottleneck - 2026-01-29.
16. OrchVis paper (arXiv 2510.24937) - https://arxiv.org/abs/2510.24937 - 2025-10-28.
17. Agent-building playbook, "Supervise Many Agents Through One Interface" - https://github.com/ramparte/agent-building-playbook/blob/ca2ab73f4837ff50d0577c09d1a55a9536072584/patterns/supervise-many-agents.md - undated.
18. Swarms issue #2044, multi-agent router discards paid responses - https://github.com/kyegomez/swarms/issues/2044 - 2026-08-25.
19. NN/g, "Skeleton Screens 101" - https://www.nngroup.com/articles/skeleton-screens/ - 2023-06-04, reviewed 2026-09-02.
20. NN/g, "Designing Empty States in Complex Applications" - https://www.nngroup.com/articles/empty-state-interface-design/ - 2021-09-19.
21. Carbon Design System, Loading pattern - https://www.carbondesignsystem.com/building-blocks/core/patterns/loading - updated 2026-08-11.
22. Carbon Design System, Empty states pattern - https://www.carbondesignsystem.com/building-blocks/core/patterns/empty-states - updated 2026-08-11.
23. Playwright, Visual comparisons - https://playwright.dev/docs/test-snapshots - accessed 2026-10-29.
24. Argos, Playwright visual regression testing in CI - https://argos-ci.com/blog/playwright-visual-regression-testing-ci - 2026-08-18.
25. Argos, Stabilize flaky tests for visual testing - https://argos-ci.com/blog/screenshot-stabilization - 2024-02-15.
26. Wopee, Screenshot comparison algorithms - https://wopee.io/blog/screenshot-comparison-algorithms-visual-testing/ - 2026-05-12.
27. microsoft/playwright issue #32057, experimental ssim-cie94 comparator - https://github.com/microsoft/playwright/issues/32057 - undated.
28. microsoft/playwright commit cac67fb, threshold with ssim-cie94 - https://github.com/microsoft/playwright/commit/cac67fb94f2c8a0ee82878054c39790e660f17ca - undated.
29. llms.txt v2 proposal - https://llmstxt.org/ - published 2024-09-03, modified 2026-08-10.
30. Open Graph protocol - https://ogp.me/ - undated.
31. Google Search Central, canonical URLs - https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls - accessed 2026-10-29.
32. Google Search Central, sitemaps overview - https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview - accessed 2026-10-29.
33. rankprobe, SEO audit in CI on a GitHub Pages site - https://dev.to/bayuh85/rankprobe-an-seo-and-ai-crawler-audit-that-fails-your-pr-before-a-stray-noindex-ships-1h1g - 2026-10-29.
34. getstarted.page, GitHub signals for developer landing-page credibility - https://getstarted.page/use-github-signals-to-build-credibility-for-developer-focuse - 2026-04-17.
35. GitHub Pages documentation - https://docs.github.com/en/pages - accessed 2026-10-29.
36. adcontextprotocol issue #5435, OTP/magic-link lockout - https://github.com/adcontextprotocol/adcp/issues/5435 - 2026-06-09.
37. OpenAI community, Case 14206599 Email OTP vanished - https://community.openai.com/t/case-14206599-email-otp-factor-vanished-from-mfa-screen-locked-out-of-paid-pro-account-no-support-response/1395376 - 2026-09-07.
38. LiteLLM issue #12383, default-tag routing overrides explicit tag - https://github.com/BerriAI/litellm/issues/12383 - undated.
39. agentgateway PR #2244, UI model/wildcard mapping fix - https://github.com/agentgateway/agentgateway/pull/2244 - undated.
40. agentgateway PR #630, wildcard model aliases - https://github.com/agentgateway/agentgateway/pull/630 - undated.
41. ClawRouter, "We Read 100 OpenClaw Issues About OpenRouter" - https://github.com/blockrunai/clawrouter/blob/7dca21323fc66905f1e69fd57565755500e579af/docs/clawrouter-vs-openrouter-llm-routing-comparison.md - 2026, undated.
42. OpenClaw issue #45663, OpenRouter provider error does not trigger failover - https://github.com/openclaw/openclaw/issues/45663 - undated.
43. OpenClaw PR #47170, classify provider error as retryable - https://github.com/openclaw/openclaw/pull/47170 - undated.
44. Cursor, "Clarifying our pricing" - https://cursor.com/en-US/blog/june-2025-pricing - 2025-07-04.
45. The News, Anthropic $16.6M invoice allegation - https://www.thenews.com.pk/latest/1408788-why-did-anthropic-charge-a-free-user-166-million-despite-zero-api-usage - 2026-07-11.
46. Audit Log Wall of Shame - https://audit-logs.tax/ - undated, accessed 2026-10-29.
47. OpenAI API reference, Audit Logs - https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/audit_logs - accessed 2026-10-29.
48. kubestellar/console issue #2647, demo data injected on API failure - https://github.com/kubestellar/console/issues/2647 - 2026-03-15.
49. kubestellar/console issue #3252, demo mode leaks real data - https://github.com/kubestellar/console/issues/3252 - 2026-03-23.
50. kubestellar/console issue #4198, demo data with local agent running - https://github.com/kubestellar/console/issues/4198 - undated.
51. kubestellar/console issue #2399, demo badge on live data - https://github.com/kubestellar/console/issues/2399 - undated.
52. headroom issue #2137, dashboard aggregates reset on restart - https://github.com/headroomlabs-ai/headroom/issues/2137 - 2026-07-13.
53. Stack Overflow question 66462559, Prometheus metrics reset by deployments - https://stackoverflow.com/questions/66462559 - undated.
54. soleur issue #6306, cross-tenant RPC disclosure - https://github.com/jikig-ai/soleur/issues/6306 - 2026-07-10.
## Executive summary

- Local-first tools win on "it just works" (HN, 2024) and lose trust on silent failure: broken pull resume, completion reported while output is truncated, and upgrades that break working models. Failure must be visible, per-artifact and recoverable.
- Adoption is real but is not satisfaction: Ollama, OpenCode, GPT4All and LocalAI all show large star counts and large open-issue backlogs; cite stars only as attention, never as quality.
- The multi-agent UX failure mode is not too few widgets; it is unscoped history replayed as live state, fabricated/sample numbers next to real KPIs, and capped lists with uncapped badges.
- Supervising a fleet is a design problem: exception-first triage, a review queue, an attention firewall, per-agent state, and cost visibility. A dashboard for one or two agents is premature.
- Dashboard practice: skeleton to the real layout for sub-10 s loads, inline/progressive loading for smaller parts, one polite live region announcing loading/busy/stuck/failed, and separate empty/error/demo/loading states.
- Dashboard state design must never substitute demo data for a failed request; that is the documented kubestellar failure and the open-mercato audit's P0.
- Playwright CI: pin one Playwright/browser (Docker image), generate and compare baselines only there, default zero tolerance, mask dynamic regions, upload traces/reports, and update baselines through a reviewed CI path. SSIM is opt-in tooling, not a default.
- Marketing credibility for dev tools = verifiable proof: live GitHub repo, claim-to-evidence links, honest "development preview", consistent canonical/OG/JSON-LD, a sitemap with truthful lastmod, and a short llms.txt. The worst signal is a dead link or a claim the repo contradicts.
- GitHub Pages project sites cannot control the origin-root robots.txt; state that plainly and use canonical/sitemap/llms.txt, or move to a custom domain for full control.
- Comparable platforms fail in repeatable classes: single-method OTP with no recovery, implicit default routes overriding explicit model choice, caps that disagree with invoices, audit logs behind enterprise tiers, demo data standing in for errors, process-local metrics resetting on deploy, and SECURITY DEFINER cross-tenant leaks.
- Most of the high-value fixes in this slice are offline-verifiable: docs/copy, dashboard state behavior, API validation of routes and budgets, static-site metadata checks, Playwright policy, and a read-only audit view. Live providers, billing, DNS/indexing, multi-tenant security and hardware remain external.
- Do not claim any externally-dependent item as verified until it has a live artifact; the repo's own evidence-ledger discipline is the correct standard.