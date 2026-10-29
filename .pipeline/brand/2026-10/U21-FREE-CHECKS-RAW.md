# U21 - Free availability / pre-screen checks (RAW)

Raw evidence log for the free pre-screen checks approved as D26. Product name
checked: "Hutch" (bare name). Retrieval date: 2026-10-28 (America/Vancouver,
PDT, UTC-07:00). Real clock at run start: 2026-10-28T23:49:54-07:00; last
request 2026-10-28T23:50:47-07:00. Per-row retrieval time is 2026-10-28 23:50 PT
(requests ran within the 53-second window above).

Pre-screen log only, not clearance; blocked sources are unreachable.

Related repo remote (context only): https://github.com/K-Arthur/hutch.git

## 1. Domain RDAP

Bootstrap URL per domain: `https://rdap.org/domain/<domain>` with
`Accept: application/rdap+json`; redirects followed (`-L`). All four resolved
to a registry RDAP endpoint and returned HTTP 200.

| Check | Exact URL | HTTP | Retrieved (PT) | Result (factual, <=200 chars) |
|---|---|---|---|---|
| RDAP hutch.com | https://rdap.org/domain/hutch.com (final: https://rdap.verisign.com/com/v1/domain/hutch.com) | 200 | 2026-10-28 23:50 | ldhName HUTCH.COM; status client delete/renew/transfer/update prohibited; registration 1995-03-02; expiration 2027-03-03; last changed 2022-10-12; registrar GoDaddy.com, LLC (IANA 146); NS NS57/NS58.DOMAINCONTROL.COM |
| RDAP hutch.app | https://rdap.org/domain/hutch.app (final: https://pubapi.registry.google/rdap/domain/hutch.app) | 200 | 2026-10-28 23:50 | ldhName hutch.app; status client delete/renew/transfer/update prohibited; registration 2018-05-08; expiration 2027-05-08; last changed 2026-06-22; registrar GoDaddy.com, LLC (IANA 146); NS ns33/ns34.domaincontrol.com |
| RDAP hutch.ai | https://rdap.org/domain/hutch.ai (final: https://rdap.identitydigital.services/rdap/domain/hutch.ai) | 200 | 2026-10-28 23:50 | ldhName hutch.ai; status client delete/renew/transfer/update prohibited; registration 2022-05-03; expiration 2028-05-03; last changed 2026-10-21; transfer 2026-04-29; registrar GoDaddy.com, LLC (IANA 146); registrant "Registration Private"; NS ns1/ns2.afternic.com |
| RDAP hutch.dev | https://rdap.org/domain/hutch.dev (final: https://pubapi.registry.google/rdap/domain/hutch.dev) | 200 | 2026-10-28 23:50 | ldhName hutch.dev; status client delete/transfer prohibited; registration 2019-03-02; expiration 2027-03-02; last changed 2026-02-20; registrar Squarespace Domains II LLC. (IANA 895); NS ns-cloud-a1..a4.googledomains.com |

Raw excerpt (hutch.com events object):
`{"eventAction":"registration","eventDate":"1995-03-02T05:00:00Z"}`,
`{"eventAction":"expiration","eventDate":"2027-03-03T05:00:00Z"}`,
`{"eventAction":"last changed","eventDate":"2022-10-12T21:58:25Z"}`.

Note: all four lookups resolved through rdap.org bootstrap; no fallback to a
registry endpoint and no "no RDAP namespace" case occurred for .ai.

## 2. GitHub API

Requests with `Accept: application/vnd.github+json` and browser UA. Unauthenticated
rate limit observed on the final header check: `x-ratelimit-limit: 60`,
`x-ratelimit-remaining: 58`. No 403/rate-limit responses occurred.

| Check | Exact URL | HTTP | Retrieved (PT) | Result (factual, <=200 chars) |
|---|---|---|---|---|
| User K-Arthur | https://api.github.com/users/K-Arthur | 200 | 2026-10-28 23:50 | login K-Arthur; name Kevin Arthur; id 58142087; type User; created 2019-11-24; public_repos 13; html_url https://github.com/K-Arthur |
| Org K-Arthur | https://api.github.com/orgs/K-Arthur | 404 | 2026-10-28 23:50 | `{"message":"Not Found","status":"404"}` (no organization K-Arthur) |
| Repo K-Arthur/hutch | https://api.github.com/repos/K-Arthur/hutch | 200 | 2026-10-28 23:50 | name hutch; id 1409280871; created 2026-10-07; public; language Python; stars 0; forks 0; description "Hutch is a local-first, MIT-licensed AI assistant platform. ..." |
| User hutch | https://api.github.com/users/hutch | 200 | 2026-10-28 23:50 | login hutch; id 4345; name Bob Hutchison; type User; created 2008-04-02; public_repos 4; html_url https://github.com/hutch |
| Org hutch | https://api.github.com/orgs/hutch | 404 | 2026-10-28 23:50 | `{"message":"Not Found","status":"404"}` (no organization hutch) |
| Repo search hutch in:name | https://api.github.com/search/repositories?q=hutch+in:name&sort=stars&order=desc&per_page=10 | 200 | 2026-10-28 23:50 | total_count 1252; incomplete_results false; top 10 below |

Search top 10 (full_name | stars | description truncated to 100 chars):
1. ruby-amqp/hutch | 876 | A system for processing messages from RabbitMQ.
2. babelouest/hutch | 22 | Experimental online password and secret locker
3. ExpeditedProjects/hutchdb | 22 | A database for AI agents. No schema, SQL, or structure required. Claude Code, Codex, Cursor, Hermes,
4. xinyangATK/GenHutch-plus-plus | 21 | The official implementation of "Optimal Stochastic Trace Estimation in Generative Modeling (AISTATS
5. jstaursky/hutch | 13 | Reversing library based off sleigh from the Ghidra project. Pcode IR access, disassembly, C++17
6. DaVikingCode/Hutch | 13 | Starling and Pixi merged in a Haxe Framework
7. RaphaelArkadyMeyerNYU/HutchPlusPlus | 13 | Code for Hutch++: Optimal Stochastic Trace Estimation
8. jonellcc/Hutchins-Bot-2.0-Fixed | 10 | (no description)
9. njern/hutch | 10 | Easily discover popular content from Twitter's public streams.
10. blackboardsh/hutch | 10 | (no description)

Raw excerpt (repo K-Arthur/hutch): `"full_name":"K-Arthur/hutch","created_at":"2026-10-07T19:30:58Z"`.

## 3. npm registry

| Check | Exact URL | HTTP | Retrieved (PT) | Result (factual, <=200 chars) |
|---|---|---|---|---|
| Package hutch | https://registry.npmjs.org/hutch | 200 | 2026-10-28 23:50 | name hutch; dist-tags.latest 0.0.1; time.created 2013-01-13; time.modified 2022-06-18; 1 maintainer; 1 version; description "keep track of all your sites with seaport and http-proxy" |
| Search hutch (near names) | https://registry.npmjs.org/-/v1/search?text=hutch&size=5 | 200 | 2026-10-28 23:50 | top names: electrobun 2.0.5 ("The lightweight npm bootstrap for Electrobun and Hutch."), hutch 0.0.1, rabbitmq-hutch 2.0.0, amqp-hutch 1.0.20, fredhutch 0.1.0 |

## 4. PyPI

| Check | Exact URL | HTTP | Retrieved (PT) | Result (factual, <=200 chars) |
|---|---|---|---|---|
| Project hutch | https://pypi.org/pypi/hutch/json | 404 | 2026-10-28 23:50 | `{"message":"Not Found"}` (no project named hutch in PyPI) |

## 5. Social handles

| Check | Exact URL | HTTP | Retrieved (PT) | Result (factual, <=200 chars) |
|---|---|---|---|---|
| X @hutch | https://x.com/hutch | 200 | 2026-10-28 23:50 | Login wall returned for anonymous request; no authenticated verification; page HTML title observed "hutch (@hutch) / X" but content is not verifiable - indeterminate/unreachable, not scraped |
| LinkedIn company hutch | https://www.linkedin.com/company/hutch | 200 | 2026-10-28 23:50 | HTTP 200, og:title "Hutch \| LinkedIn", og:description "Hutch \| 881 followers on LinkedIn." - public metadata only; rest behind sign-in wall |
| LinkedIn in/hutch | https://www.linkedin.com/in/hutch | 200 | 2026-10-28 23:50 | HTTP 200, page title "Jimmy Hutcheson - SPIN \| LinkedIn" - public profile metadata only; rest behind sign-in wall |
| YouTube @hutch | https://www.youtube.com/@hutch | 200 | 2026-10-28 23:50 | HTTP 200; <title> "Hutch - YouTube"; og:title "Hutch"; channelId UCq54nlcoX-0pLcN5RhxHyug; not a 404 page |
| YouTube c/hutch | https://www.youtube.com/c/hutch | 200 | 2026-10-28 23:50 | HTTP 200; redirects/renders same channel: <title> "Hutch - YouTube"; channelId UCq54nlcoX-0pLcN5RhxHyug |
| Bluesky resolveHandle | https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle=hutch.bsky.social | 400 | 2026-10-28 23:50 | `{"error":"InvalidRequest","message":"Unable to resolve handle"}` (handle not registered) |
| Bluesky profile URL | https://bsky.app/profile/hutch.bsky.social | 200 | 2026-10-28 23:50 | HTTP 200 is the static web-app shell only (title "Bluesky"); content is client-rendered and returned no profile data; not evidence of a profile. Authoritative resolveHandle API returned unregistered. |

## Notes / method

- Transport: `curl -sS -L -m 20 -A '<browser UA>' -H '<Accept ...>' -o <tmp> -w '%{http_code}|%{url_effective}'`.
  `-L` followed redirects and the final URL is recorded above. JSON parsed with
  `.venv/bin/python` using the json module. No `uv sync`/`uv run` was used.
- RDAP: `Accept: application/rdap+json`; rdap.org bootstrap only.
- GitHub: `Accept: application/vnd.github+json`; unauthenticated. Rate limit
  at 58/60 remaining after the checks; no 403 occurred.
- No page scraping of X; X response is recorded as indeterminate per protocol.
  LinkedIn responses were read only at the HTTP/title/metadata level.
- All requests were single unauthenticated GETs. No login, no account creation,
  no form submission.
- Total HTTP requests in this log: 23 (4 RDAP + 6 GitHub + 2 npm + 1 PyPI +
  8 social + 1 LinkedIn re-check + 1 GitHub header re-check).
- All requests completed; servers did not time out. A 403/CAPTCHA/999 or timeout
  would be recorded as unreachable, never as clear or not found. No such case
  occurred here except the X login wall (recorded as unreachable/indeterminate).
- "Registered" / "exists" below means the response shows an existing record; it
  is not a legal conclusion and not a clearance decision.

## Coverage summary

| Check | Category | Date |
|---|---|---|
| RDAP hutch.com | registered | 2026-10-28 |
| RDAP hutch.app | registered | 2026-10-28 |
| RDAP hutch.ai | registered | 2026-10-28 |
| RDAP hutch.dev | registered | 2026-10-28 |
| GitHub user K-Arthur | exists | 2026-10-28 |
| GitHub org K-Arthur | not-found | 2026-10-28 |
| GitHub repo K-Arthur/hutch | exists | 2026-10-28 |
| GitHub user hutch | exists | 2026-10-28 |
| GitHub org hutch | not-found | 2026-10-28 |
| GitHub search hutch in:name | exists (1252 repos) | 2026-10-28 |
| npm package hutch | registered | 2026-10-28 |
| npm search near names | exists (near-name packages) | 2026-10-28 |
| PyPI project hutch | not-registered | 2026-10-28 |
| X @hutch | unreachable (login wall / indeterminate) | 2026-10-28 |
| LinkedIn company hutch | exists (public metadata) | 2026-10-28 |
| LinkedIn in/hutch | exists (public profile metadata) | 2026-10-28 |
| YouTube @hutch | exists | 2026-10-28 |
| YouTube c/hutch | exists (same channel) | 2026-10-28 |
| Bluesky handle hutch.bsky.social | not-registered | 2026-10-28 |
| Bluesky profile URL (shell only) | error (no profile data via HTTP) | 2026-10-28 |

Pre-screen log only, not clearance; blocked sources are unreachable.
