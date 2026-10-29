# IP-CLEARANCE.md - "Hutch" knockout pre-screen log

Status: PRE-SCREEN, NOT CLEARANCE - OPEN for counsel
Date: 2026-10-28 (America/Vancouver)
Run: 3 - Project: Hutch - Artifact dir: .pipeline/brand/2026-10
Author: teammate "knockout" (DSH session), for the brand identity lead
Scope: name "Hutch" (wordmark forms hutch / hutch. / Hutch, plus combined forms "Hutch app",
"Hutch AI", "Hutch assistant"); Nice classes 9 and 42 only; territories US, EU, UK, Canada
(DECISION D13); free registers only, zero external spend (DECISION D15); written risk ownership
posture (DECISION D20). No asset was generated, drawn or rendered for this artifact; text only.
Plan gate G1 remains OPEN: no mark, name or tagline asset may be generated before
CLEARANCE-PROTOCOL.md exists and is signed off.

Reporting convention (plan G6): this document is "pre-screen, not clearance". Results are
"risk rated". Nothing here is "cleared to the extent documented"; that phrase is reserved for
counsel's later work, if funded. No clearance, distinctiveness or non-infringement conclusion is
drawn anywhere in this file.

---

## 0. STOP CONDITION - ESCALATION REQUIRED (observed overlap)

A HUTCH word mark was observed as LIVE and REGISTERED in the United Kingdom and as a NEW
APPLICATION FILED in the United States. Both entries are in the core territories. Whether either
entry covers Nice class 9 or 42 is NOT VERIFIED: every page that would show the class was
unreachable in this pre-screen (HTTP 403 bot-block, fetch failure, or JS-only app). If either
entry covers class 9 or 42, the observed overlap is direct for the planned scope. This was
escalated to the lead on 2026-10-28 before the search continued.

| # | Entry (as seen) | Register / territory | Serial / number | Status (as seen) | Holder (as seen) | Class (as seen) | Source URL + retrieval date |
|---|---|---|---|---|---|---|---|
| H1 | HUTCH | USPTO, United States (via aggregator) | 99695333 | "LIVE ... NEW APPLICATION FILED" | not visible | NOT VISIBLE - UNVERIFIED | https://www.trademarkelite.com/trademark/trademark-detail/99695333/HUTCH (retrieved 2026-10-28) |
| H2 | HUTCH | UKIPO, United Kingdom (via aggregator) | UK00003791602 | "LIVE Current Status - Registered" | not visible | NOT VISIBLE - UNVERIFIED | https://www.trademarkelite.com/uk/trademark/trademark-detail/UK00003791602/HUTCH (retrieved 2026-10-28) |
| H3 | HUTCH (numbers seen as UK designations of international registrations) | UKIPO, United Kingdom | UK00902129492; UK00915655715 | not visible | not visible | NOT VISIBLE - UNVERIFIED | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00902129492 and https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00915655715 (retrieved 2026-10-28) |
| H4 | HUTCH (word mark) | DPMA, Germany (outside the four core territories) | not visible | not visible | Hutch Games Ltd. | NOT VISIBLE - UNVERIFIED | https://www.northdata.de/?id=6347513561 (retrieved 2026-10-28) |
| H5 | HUTCH filings by holder | USPTO, United States (owner index) | not visible | not visible | Hutch Technologies, LLC | NOT VISIBLE - UNVERIFIED | https://www.trademarkelite.com/trademark/trademark-owner/Hutch%20Technologies,%20LLC (retrieved 2026-10-28) |

Verbatim wording observed (search-result title text, 2026-10-28):

- H1: "HUTCH Trademark (USPTO Serial 99695333) | USPTO Record | TrademarkElite - LIVE On 3/11/2026 - NEW APPLICATION FILED"
- H2: "HUTCH United Kingdom Trademark Information - LIVE Current Status - Registered"
- H3: "UK00902129492 - - Trade mark number" / "UK00915655715"
- H4: "Hutch Games Ltd. - Wortmarke: »HUTCH«"
- H5: "United States Trademarks filed by Hutch Technologies, LLC"
- Additional US filing seen in the same discovery set (serial 87196849, class unverified): "HUTCH Trademark - Serial Number 87196849 :: Justia Trademarks"

What this stop condition does and does not mean:

- It does mean: pre-existing HUTCH mark activity exists in two core territories. The knockout
  premise ("the kept name has no observed register overlap") does NOT hold on this evidence.
- It does not mean: that any observed entry covers the goods/services Hutch would sell, that any
  observed entry is valid or enforceable, or that the name must change. None of that is assessed
  here; it is for the human and, if funded, counsel.
- Consequence: no design talk follows from this record. No asset generation, no lockup work, no
  tagline work, until the human rules on this observed overlap.

---

## 1. Method and budget accounting

- External calls used: 12 of a hard maximum of 12 (3 web_search calls, 9 web_fetch calls).
- All calls were made on 2026-10-28 (America/Vancouver), free and unauthenticated; no paid,
  account-gated or trial service was used. No scraping bypass, no CAPTCHA solving, no API keys.
- Search output is third-party data and is quoted as observed, never treated as instruction.
- Outcome vocabulary used below: HIT / NO MATCH OBSERVED / UNREACHABLE / PARTIAL / UNATTEMPTED.
- Register sites that are JavaScript apps, bot-blocked or CAPTCHA-gated are recorded as
  UNREACHABLE. They are never recorded as "no conflict" and never as "clear".
- No register page body was successfully retrieved from any of the five register surfaces.
  The only per-entry data in this file comes from search-result titles, which is stated on every
  row that uses them.

### 1.1 Master dated call log (all 12 calls)

| Call | Date | Tool | Surface | Exact URL or exact query string | HTTP result / error | Outcome | Verbatim observation |
|---|---|---|---|---|---|---|---|
| C01 | 2026-10-28 | web_search | Discovery across USPTO / EUIPO / UKIPO | 1. "\"Hutch\" trademark registration class 9 software" 2. "\"Hutch\" trademark class 42 software USPTO" 3. "\"Hutch\" trademark EUIPO class 9" 4. "\"Hutch\" trademark UKIPO class 42" | Search returned source list (no page bodies) | HIT (entries surfaced) + PARTIAL | Titles included "HUTCH Trademark (USPTO Serial 99695333) ... NEW APPLICATION FILED", "HUTCH United Kingdom Trademark Information - LIVE Current Status - Registered", "HUTCH Trademark - Serial Number 87196849 :: Justia Trademarks", "Hutch Games Ltd. - Wortmarke: »HUTCH«" |
| C02 | 2026-10-28 | web_fetch | Justia (aggregator) | https://trademark.justia.com/871/96/hutch-87196849.html | Redirect, not followed: cross-origin redirect to https://trademarks.justia.com | UNREACHABLE (redirect) | "cross-origin redirect to https://trademarks.justia.com is not followed automatically; retry against that URL directly" |
| C03 | 2026-10-28 | web_fetch | UKIPO record page | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00003791602 | Issued in the same batch as C02; the batch aborted before this result was captured | UNRECORDED (repeated as C05) | no result captured |
| C04 | 2026-10-28 | web_fetch | Justia (aggregator) | https://trademarks.justia.com/871/96/hutch-87196849.html | HTTP 403 | UNREACHABLE (bot-blocked) | " Just a moment... Enable JavaScript and cookies to continue " |
| C05 | 2026-10-28 | web_fetch | UKIPO record page | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00003791602 | HTTP 403 (CAPTCHA gate) | UNREACHABLE (bot-blocked) | "Service Captcha &ndash; Apply to register a trade mark – Intellectual Property Office" |
| C06 | 2026-10-28 | web_fetch | Aggregator: UK HUTCH detail | https://www.trademarkelite.com/uk/trademark/trademark-detail/UK00003791602/HUTCH | HTTP 403 | UNREACHABLE (bot-blocked) | " Just a moment... Enable JavaScript and cookies to continue " |
| C07 | 2026-10-28 | web_search | Vienna codes + common-law | 1. "Vienna classification code hexagon polygon 26.05 trademark design" 2. "Vienna Agreement \"26.05.01\" OR \"26.05.03\" hexagon" 3. "\"Hutch\" AI assistant app software company" 4. "github K-Arthur hutch" | Search returned source list (no page bodies) | PARTIAL / NO MATCH OBSERVED for Vienna definitions and GitHub check | No Vienna code definition returned. No github.com/K-Arthur result returned (returns were Korean-language K-language articles and unrelated pages). Titles seen included "OVERLAPPING HEXAGON DESIGN-2318410" (a CIPO record PDF) and "Quit Smoking With Help From Fred Hutch's Free AI-Powered Chatbot" |
| C08 | 2026-10-28 | web_fetch | EUIPO eSearch | https://euipo.europa.eu/eSearch/#basic/hutch | Fetch failed: TypeError: fetch failed | UNREACHABLE (JS app / network) | "web fetch failed: TypeError: fetch failed" |
| C09 | 2026-10-28 | web_fetch | WIPO Global Brand Database | https://branddb.wipo.int/en/quicksearch?q=hutch | Fetch failed: unsupported content type "unknown" | UNREACHABLE (JS app) | "unsupported content type \"unknown\"" |
| C10 | 2026-10-28 | web_search | Class verification + domain discovery | 1. "\"99695333\" HUTCH trademark class" 2. "\"UK00003791602\" HUTCH class 9" 3. "Hutch Games Ltd trademark \"class 9\" \"class 41\"" 4. "hutch.com domain Hutch software" | Search returned source list (no page bodies) | NO CLASS MATCH OBSERVED (class still UNVERIFIED) | No class number appeared in any returned title. Titles seen: "United States Trademarks filed by Hutch Technologies, LLC", "UK00915655715", "Hutch - Crunchbase Company Profile & Funding", "Hutch - 2026 Company Profile & Team - Tracxn" |
| C11 | 2026-10-28 | web_fetch | Aggregator mirror: UK HUTCH detail | https://legalforcetrademarkia.com/uk/hutch-UK00003791602.htm | Fetch failed: TypeError: fetch failed | UNREACHABLE | "web fetch failed: TypeError: fetch failed" |
| C12 | 2026-10-28 | web_fetch | CIPO trademark search | https://ised-isde.canada.ca/cipo/trademark-search/ | Redirect, not followed: cross-origin redirect to http://ised-isde.canada.ca | UNREACHABLE (redirect; 12-call cap reached) | "cross-origin redirect to http://ised-isde.canada.ca is not followed automatically; retry against that URL directly" |

Budget note: C12 consumed the twelfth and final permitted call; the redirect target was not
retried and no further external calls were made. C03 is counted as a used call because the
request was issued, even though its result was lost to a batch error.

---

## 2. Per-register sections

### 2.1 USPTO Trademark Search (tmsearch.uspto.gov) - surface 1

Direct USPTO search was NOT attempted within budget: the eight calls after discovery were
consumed by blocked aggregators (C02-C06, C11), two failed register apps (C08, C09), and class
verification searches (C10). US evidence is therefore aggregator-snippet evidence only.

| Call | Date | Source | URL or query | Result | Outcome |
|---|---|---|---|---|---|
| C01 | 2026-10-28 | search discovery | query set 1 (see 1.1) | HUTCH serial 99695333 surfaced; HUTCH serial 87196849 surfaced | HIT (entry observed, class unverified) |
| C02 | 2026-10-28 | Justia | https://trademark.justia.com/871/96/hutch-87196849.html | redirect not followed | UNREACHABLE |
| C04 | 2026-10-28 | Justia | https://trademarks.justia.com/871/96/hutch-87196849.html | HTTP 403 Cloudflare | UNREACHABLE |
| C10 | 2026-10-28 | search for classes | queries 1 and 3 (see 1.1) | no class number in any title; owner index "Hutch Technologies, LLC" surfaced | NO CLASS MATCH OBSERVED |

Findings: at least two US HUTCH filings exist on this evidence (serials 99695333 and 87196849),
plus a US owner index for "Hutch Technologies, LLC". Serial 99695333 is described by the
aggregator title as a new application filed; the phrase in the title reads "LIVE On 3/11/2026 -
NEW APPLICATION FILED" (date format as published by the aggregator; not interpreted here).
Class, goods/services, holder of record and status per the USPTO register are all UNVERIFIED.
Residual risk: HIGH - unresolved observed overlap; direct USPTO lookup is the single highest-value
next step.

### 2.2 EUIPO eSearch (euipo.europa.eu/eSearch) - surface 2

| Call | Date | Source | URL or query | Result | Outcome |
|---|---|---|---|---|---|
| C08 | 2026-10-28 | EUIPO eSearch | https://euipo.europa.eu/eSearch/#basic/hutch | TypeError: fetch failed | UNREACHABLE |

Findings: no EU entry could be observed. eSearch is a JavaScript application with a hash-fragment
query URL, so a static fetch cannot return results. This is an access failure, not an absence of
records. EU trademark coverage is UNASSESSED. Residual risk: UNKNOWN - must be treated as high
exposure until a human runs the search in a browser.

### 2.3 TMview (tmdn.org/tmview) - surface 2b

Not attempted. Budget was exhausted on the surfaces listed above. TMview is a JavaScript
aggregator; no result exists in this pre-screen. Residual risk: UNKNOWN.

### 2.4 WIPO Global Brand Database (branddb.wipo.int) - surface 3

| Call | Date | Source | URL or query | Result | Outcome |
|---|---|---|---|---|---|
| C09 | 2026-10-28 | WIPO Global Brand Database | https://branddb.wipo.int/en/quicksearch?q=hutch | "unsupported content type unknown" | UNREACHABLE |

Findings: no WIPO record could be observed. The application returns a JavaScript shell, so a
static fetch yields no results. This is an access failure, not an absence of records. The WIPO
database also aggregates the US/UK/EU/CA data already partly covered above, so it does not
replace the direct lookups. Residual risk: UNKNOWN.

### 2.5 UKIPO (trademarks.ipo.gov.uk) - surface 4

| Call | Date | Source | URL or query | Result | Outcome |
|---|---|---|---|---|---|
| C03 | 2026-10-28 | UKIPO record page | https://trademarks.ipo.gov.uk/ipo-tmcase/page/Results/1/UK00003791602 | issued; result lost to batch error | UNRECORDED |
| C05 | 2026-10-28 | UKIPO record page | same URL | HTTP 403 CAPTCHA | UNREACHABLE |
| C06 | 2026-10-28 | Aggregator detail page for the UK record | https://www.trademarkelite.com/uk/trademark/trademark-detail/UK00003791602/HUTCH | HTTP 403 | UNREACHABLE |
| C11 | 2026-10-28 | Aggregator mirror for the UK record | https://legalforcetrademarkia.com/uk/hutch-UK00003791602.htm | TypeError: fetch failed | UNREACHABLE |
| C01 | 2026-10-28 | search discovery | query set 1 | UK00003791602 surfaced as "LIVE ... Registered" | HIT (entry observed, class/holder unverified) |

Findings: UK00003791602 HUTCH is described by the aggregator title as LIVE and REGISTERED.
A second UK number, UK00915655715, and UK00902129492 were surfaced (the latter also in C01);
the UK009... number format is consistent with UK designations of international registrations, but
that is not asserted here as verified. Classes, holder, filing date and goods/services are all
UNVERIFIED. The UKIPO record page itself is CAPTCHA-gated to automated access. Residual risk:
HIGH - registered HUTCH mark in a core territory; the stop condition stands.

### 2.6 CIPO (ised-isde.canada.ca / ic.gc.ca) - surface 5

| Call | Date | Source | URL or query | Result | Outcome |
|---|---|---|---|---|---|
| C12 | 2026-10-28 | CIPO trademark search | https://ised-isde.canada.ca/cipo/trademark-search/ | cross-origin redirect to http://ised-isde.canada.ca | UNREACHABLE (redirect; cap reached) |

Findings: no Canada entry could be observed and no Canadian search was executed. This is an
access failure, not an absence of records. Canada is a core territory in scope, so Canadian
coverage is UNASSESSED. Residual risk: UNKNOWN.

---

## 3. WIPO Vienna design-code findings (surface 6)

Status: NO VERIFIED CODE DEFINITIONS. This section records an evidence gap, not a classification.

- Intended search: Vienna Classification (design elements) codes for the device described as a
  hexagon outline with a centre dot, i.e. a polygon outline plus a small circular element inside it.
- Attempted: C07 search queries 1 and 2 (Vienna classification, hexagon, polygon, candidate code
  numbers). Result: no WIPO or EUIPO Vienna code list was returned; no code definition was
  observed in the returned source titles.
- Not attempted: a direct fetch of the WIPO Vienna classification browser (no budget left after
  the stop-condition escalation and class-verification calls).
- Therefore: no Vienna code, division number or code definition is verified in this document.
  Do not cite any code from this file in a filing, a records request or a counsel brief.

Why this matters and does not matter: Vienna codes index figurative elements and are used for
register search and filing strategy. They do not change the name-overlap stop condition above,
which is a word-mark question. The device element does, however, need proper coding before any
figurative search is meaningful, so the gap is carried as an action, not a finding.

Unverified area to check manually (do not treat as evidence): the current Vienna edition's
division for polygons and the subdivision that covers polygons enclosing a circle or dot. The
human should open the WIPO Vienna browser, note the edition number and retrieval date, and record
the code definitions verbatim in a later run.

Residual risk rating for the device path: MEDIUM - unassessed figurative overlap; no code, no
figurative search, no result.

---

## 4. Common-law, web, GitHub, handle and domain findings (surface 7)

### 4.1 Web / brand-use signals

| Call | Date | Query | Observation | Outcome |
|---|---|---|---|---|
| C01 | 2026-10-28 | "Hutch" trademark class 9/42/UKIPO/EUIPO discovery queries | Existing HUTCH mark activity: US serials 99695333 and 87196849; UK00003791602 registered; Hutch Games Ltd word mark; a CN aggregator record; a Hong Kong journal record | HIT (signals observed) |
| C07 | 2026-10-28 | "\"Hutch\" AI assistant app software company"; "github K-Arthur hutch" | No Hutch-branded software or AI product surfaced among returned titles in the first query result set; the GitHub query returned unrelated Korean-language K-language articles | NO MATCH OBSERVED (weak negative; source list only) |
| C10 | 2026-10-28 | "hutch.com domain Hutch software"; class-verification queries | Company profiles for entities named "Hutch" surfaced (Crunchbase, Tracxn); no domain-status page surfaced; no class number surfaced | PARTIAL / NO MATCH OBSERVED for domain status |

Reading of the web signals: "Hutch" is used by more than one commercial entity, including at
least one games company and at least one technology-named LLC, and the word is a common English
noun. The observation supports a risk rating, not a conclusion. Common-law use in the planned
goods/services was not analysed; that is legal work, not a search.

### 4.2 GitHub / organisation check

- github.com/K-Arthur was NOT checked (no budget). C07's GitHub-targeted query returned no
  relevant result, which is not evidence about the account or its repositories.
- No repository, npm package or PyPI package check was performed.

### 4.3 Social handles

- Not attempted. No handle presence data exists in this pre-screen for X, LinkedIn, YouTube,
  Bluesky, Instagram or Discord.

### 4.4 Domains (RDAP)

- Not attempted. The planned checks were https://rdap.verisign.com/com/v1/domain/hutch.com and
  https://rdap.org/domain/<name> for the .app/.ai/.dev variants. Domain availability in 2026 is
  not determinable from this document.

### 4.5 Combined-form phrase check

- "Hutch app", "Hutch AI" and "Hutch assistant" were not searched as exact phrases. The discovery
  queries used the bare name. No combined-form result exists in this pre-screen.

Residual risk rating for common-law/handles/domain: MEDIUM-HIGH - multi-entity use of the word is
visible, the account and domain state is unknown, and no analysis of goods/services proximity has
been done.

---

## 5. Summary table - every register and surface, with outcome and residual risk

| Surface | Attempted? | Call(s) | Outcome | Residual risk (risk rated) | Why that rating |
|---|---|---|---|---|---|
| USPTO Trademark Search (direct) | No - budget | none | UNATTEMPTED | HIGH / UNKNOWN | HUTCH filings observed via aggregator; classes unverified; no direct register check |
| US aggregators (Justia, TrademarkElite) | Yes | C02, C04, C06, C10, C11 | UNREACHABLE (403 / fetch failure) | HIGH | entries observed in snippets only; no class or holder confirmation |
| EUIPO eSearch | Yes | C08 | UNREACHABLE (fetch failed) | UNKNOWN - treat as high | no EU data at all; JS app, static fetch impossible |
| TMview | No - budget | none | UNATTEMPTED | UNKNOWN | no cross-register view obtained |
| WIPO Global Brand Database | Yes | C09 | UNREACHABLE (content type) | UNKNOWN | no WIPO data at all; JS app |
| UKIPO | Yes | C03, C05, C06, C11 | UNREACHABLE (CAPTCHA 403) | HIGH | registered HUTCH mark observed; class unverified |
| CIPO | Yes | C12 | UNREACHABLE (redirect; cap) | UNKNOWN | no Canadian data at all |
| WIPO Vienna codes | No (search only) | C07 | PARTIAL - no code verified | MEDIUM (device path) | no code, no figurative search |
| Common-law web | Partial | C01, C07, C10 | HITS/NO MATCH mix | MEDIUM-HIGH | multi-entity use visible; no goods/services analysis |
| GitHub / packages | No | none | UNATTEMPTED | UNKNOWN | account and package state unknown |
| Social handles | No | none | UNATTEMPTED | UNKNOWN | handle state unknown |
| Domains (RDAP) | No | none | UNATTEMPTED | UNKNOWN | domain state unknown |

Overall: this pre-screen is OPEN. It contains one stop condition (H1/H2) and no register surface
was successfully read. Nothing here supports a "no conflict" statement in any territory.

---

## 6. What this pre-screen does NOT establish

- It does not establish clearance, availability, registrability, distinctiveness or
  non-infringement for "Hutch" or for the hexagon-and-dot device, in any territory.
- It does not establish that the observed HUTCH entries cover Nice class 9 or 42; the class field
  was unreadable on every source. Equally, it does not establish that they do not.
- It does not establish the holder, status, filing date, priority date or goods/services of the
  observed entries, beyond the aggregator title wording quoted in section 0.
- It does not establish anything about the European Union, Canada, TMview or the WIPO Global Brand
  Database: those surfaces were unreachable or unattempted, and an unreachable register is not a
  clean register.
- It does not establish the domain, social handle, GitHub or app-store position for "Hutch".
- It does not establish Vienna design codes for the device; no code definition was verified.
- It does not assess combined forms ("Hutch app", "Hutch AI", "Hutch assistant"), common-law
  rights, use in commerce, likelihood-of-confusion factors or filing strategy. Those need a human
  decision and, if funded, counsel.
- It is not legal advice and does not substitute for the review required by plan gate G1.

## 7. Recommended next actions for the human

1. Free manual confirmation of the stop condition, in a normal browser (no spend): open
   tmsearch.uspto.gov and look up serial 99695333 and 87196849; open trademarks.ipo.gov.uk and
   look up UK00003791602, UK00915655715 and UK00902129492. Record for each: holder, status,
   Nice classes, goods/services wording, filing and priority dates, and the page URL with the
   retrieval date. This is the single highest-value next step and resolves whether the overlap is
   direct.
2. If either entry covers class 9 or 42, treat the name as an observed overlap and decide
   explicitly: proceed with written risk ownership (D20), narrow the goods/services description,
   or reconsider the name. Record the decision in DECISION.md with date and rationale.
3. Run the remaining free register searches manually and paste the results into this log:
   EUIPO eSearch, TMview, WIPO Global Brand Database, CIPO (classes 9 and 42, territories
   US/EU/UK/CA). Add a new dated call row for each; do not mark any of them "clear".
4. Have the hexagon-and-dot device coded against the current Vienna edition, and record the
   edition number, code numbers and verbatim definitions. Do not let any code in this file reach a
   filing.
5. Check domains via RDAP (hutch.com plus .app/.ai/.dev variants) and the handle set (GitHub
   including github.com/K-Arthur, X, LinkedIn, YouTube, Bluesky), and record registration and
   handle status with dates.
6. Search the combined forms as exact phrases and the app stores for "Hutch" apps in the
   productivity/AI category; record any observed app names and publishers.
7. Fund counsel for a proper full search before any filing spend, or re-confirm the written risk
   ownership decision (D20/B6) at the gate. This pre-screen does not replace that step.
8. Keep plan gate G1 closed: no mark, wordmark, tagline or lockup asset is generated until
   CLEARANCE-PROTOCOL.md exists and is signed off, and until the human rules on this stop
   condition.

## 8. Unattempted searches (recorded, not hidden)

Budget was exhausted at 12 external calls. The following were planned by scope and NOT executed:

- USPTO tmsearch.uspto.gov direct search: word mark "hutch", classes 9 and 42, live and dead,
  US; plus serials 99695333 and 87196849 detail pages.
- EUIPO eSearch detail search for "hutch", Nice 9 and 42, EU; TMview cross-register search.
- WIPO Global Brand Database search for "hutch", classes 9 and 42, in US/EM/GB/CA collections.
- CIPO Canadian Trademarks Database search for "hutch", classes 9 and 42.
- WIPO Vienna classification browser: hexagon/polygon outline plus centre-dot codes, current
  edition, verbatim definitions.
- RDAP domain checks: https://rdap.verisign.com/com/v1/domain/hutch.com and rdap.org for
  hutch.app, hutch.ai, hutch.dev, gethutch.com.
- GitHub checks: github.com/K-Arthur profile and repositories, org and repo name "hutch",
  npm/PyPI package names.
- Social handle checks: X, LinkedIn, YouTube, Bluesky, Instagram, Discord.
- App-store checks: Apple App Store and Google Play for apps named "Hutch".
- Exact-phrase searches: "Hutch app", "Hutch AI", "Hutch assistant".
- UKIPO journal and international-registration detail for UK00902129492 / UK00915655715.
- Any paid or account-gated register tool (excluded by budget D15; not attempted).

## 9. Evidence index

Every source line above carries URL + retrieval date 2026-10-28. Files and registers referenced:
USPTO trademark search surface (not read), EUIPO eSearch (C08), WIPO Global Brand Database (C09),
UKIPO record pages (C03/C05), CIPO search (C12), aggregator pages (C02/C04/C06/C11), search
results (C01/C07/C10), WIPO Vienna browser (not fetched). No external page body was successfully
retrieved from any register; all per-entry data is from search-result title text as quoted.

Open state: PRE-SCREEN, NOT CLEARANCE - OPEN for counsel. Stop condition recorded in section 0 and
reported to the lead on 2026-10-28.
