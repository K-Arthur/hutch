# Claims audit (2026-10-07)

Every public statement that exceeded the evidence, what it said, what the evidence supports, and what changed. "Reinstate when" says
which verified behaviour would let a stronger statement come back.

| Where | Claim (was) | Evidence | Now says | Reinstate when |
|---|---|---|---|---|
| website, README | "Strict sandboxing", "Workspace jail ... isolated workspace" | The shell runs as the user (baseline lead 9) | "Policy engine and workspace path jail ... not an operating-system sandbox" | S4 lands and `T-SANDBOX` passes on a supporting host |
| website | "Public-only egress: blocked from localhost, internal subnets, cloud metadata" | 7 loopback/metadata forms and redirects allowed (D3) | "Not yet: DNS/redirect-aware fetch checks" | **Landed in S1** (`T-SSRF`, 99 tests); the website now states the fetch checks, with the browser's residual DNS-rebinding window documented |
| website | "Per-bot mutexes guarantee scheduled tasks never clobber each other" | Single-process lock only (lead 2); cross-process Stop failed (D1) | "A bot never overlaps itself inside one process; cross-process claims in progress" | S2 + S3 land (`T-CLAIM-RACE`, `T-OCCURRENCE-RACE`) |
| website, README | "Hard spending caps" | Daily *token* cap and priced spend caps exist; wall-clock kill abandons a thread; no reservation (leads 1, 6) | "Caps: ... a token cap is not a currency cap" | S3 + reservation work (`T-RESERVE`) |
| website | "$447, silently billed overnight (GitHub bug report, May 2026)" | No source recorded or found (C6) | Removed; card now describes the failure class and what is verified | A primary source is found |
| website | Incident 02 cited HN #42749402 | That item is "Show HN: Interactive systemd" (D6) | Cites two relevant HN comments | - |
| website | Incident 03 quote presented as verbatim | The text was a paraphrase | Titles of the two HN items, labelled as reports | - |
| website | Incident 04 "bypassed allowlists for a year" | The cited comment does not say how long (C5) | The comment's actual claim | A dated fix/issue is found |
| website | Incident 05 "OpenClaw shipped with zero out-of-the-box restrictions ... post-mortem" | Cited HN item is a commenter's question (D6); no post-mortem exists in the sources | Replaced with the verified OpenClaw issue #138499, labelled open/unreproduced, plus Hutch's own matching weakness | - |
| website | Comparison table columns for Meta Muse and OpenClaw ("Zero guardrails", "Zero isolation", "None (unlimited)"), Grok "Home folder leaks", dots "$20+/mo", "GPT only" | No primary source read for Muse/OpenClaw; the Grok upload report was about a different product (Grok CLI); dots page lists Pro/Business/Enterprise availability, no $20 tier | Columns removed; remaining cells quote the vendors' own pages (A1-A3) and say "not documented" where we could not read | We read the vendor's own documentation |
| website | "~300 line auditable loop" | `runtime/builtin.py` is 545 lines | "built-in agent loop" | - |
| website | "Linux, macOS, WSL" | Only Linux is exercised; classifier says POSIX :: Linux | "Linux (macOS and Windows not supported yet)" | CI on those platforms |
| website | "0 telemetry", "zero phone-home, zero accounts, and zero analytics" | Searched `src/` for telemetry/analytics/phone-home: none. But hosted models and web tools do send data | "No telemetry in hutch itself" plus an explicit paragraph on what *does* leave the machine | - |
| website | "Persistent logins ... Chromium profiles persist per bot" | Context is class-global; second bot reuses the first bot's profile (lead 8) | "experimental"; known gaps listed | S7 (`T-BROWSER-ISOLATION`) |
| website | Install: `pip install hutch`, `git clone github.com/K-Arthur/hutch`, "Read the Source on GitHub", header GitHub pill | Anonymous GET of the repo returns 404 (D5); PyPI name unclaimed | "Not published yet; install from a source checkout"; dead links removed | The repository or package is actually published (an authorised decision) |
| README | "71 tests" | 637 pass | 637, with the e2e caveat | - |
| README | "Any model", "full transcripts", "never overlapping runs", "Browser with memory" | See the claim matrix in `baseline.md` | Qualified individually | per item |
| README / safety | "Container-per-run isolation is on the roadmap" | OS sandbox now specified (ADR-0006) | Points to the ADR and slice | - |
| docs/research | $447, $2,300 in 48 h, "open ~1 year", HN item mis-citations, anecdotes presented as incidents | `evidence-ledger.md` C and D | Quarantined or corrected in place, banner added | primary sources |
| docs/research | OpenClaw and Muse allegations | Only titles/comments were read | Marked as reports | - |

## Things that stay and are true

* "No telemetry in hutch itself" (source search) - kept, with the data-flow caveat.
* "Unanswered approvals expire as denied" - tested (`tests/test_engine.py`).
* "DST-correct cron" - covered by `tests/test_scheduler.py` (single process).
* The compound-command parser claims - fuzzed in `tests/test_shellparse.py`; scope stated as policy, not containment.
