# Connectors, integrations, plugins and skills: delivery status

Status date: 2026-10-30. Base: `main`. This file records what is implemented, what was verified,
and what is still missing. It is written to be checkable: every claim names the file or command
that supports it.

## 1. What was found at the start

The brief asked for a governed ecosystem of connectors, integrations, plugins and skills. The
initial reading of the repository found more already built than the brief assumed, and one large
piece of completed work stranded outside `main`:

- ADR-0017 S0/S1 had landed on `main` (typed integration identities, the consent ladder, schema
  v73 tables, the derived tool catalog). The ADR's own status text was stale and said no MCP
  transport existed; `main` also had a Notion MCP read integration using the pinned SDK.
- `main` was at schema v84, not the v73 the ADR described.
- The `agent-connections` lane (tip `3c5ce893`, 63 commits ahead of a merge base 772 commits
  behind) contained a full MCP plane, a credential vault, OAuth refresh serialisation and
  substantial skills work. It was not merged, was on schema 56, and touched 131 files that `main`
  had also changed. Porting it wholesale would have replayed 772 commits of drift.
- Tool argument validation ran in the built-in model loop only. Workflow nodes and the OpenCode
  bridge dispatched unvalidated arguments; authority was whatever each tool chose to consult.

Because 772 commits of independent drift cannot be reconciled safely in one step, the stranded
lane was treated as a reference implementation rather than a merge source, and the capabilities
were rebuilt on `main`'s current contracts. That decision is the main judgement in this delivery.

## 2. What is implemented

### 2.1 Dispatch-level enforcement (commit `934e1b69`)

`src/hutch/runtime/dispatch.py` holds one pre-dispatch check that `runtime/steps.py::call_tool`
runs for every caller: first the integration grant (re-read from the store, never cached), then
the canonical argument schema. `src/hutch/integrations/grants.py` holds the two grant queries so
configuration (`integration_tool_names`) and enforcement (`integration_tool_granted`) use the same
enabled-and-operation-authorized join. `src/hutch/runtime/artifacts.py` took the artifact writer
out of `runtime/steps.py`, so both frozen over-cap files shrank rather than grew.

### 2.2 MCP client plane (commit `fd3002a4`)

`src/hutch/integrations/mcp/`:

- `config.py` validates definitions: argv only (no shell), executable must be under `/usr` or a
  reviewed mount, mount and credential screening, fingerprints for the executable and every
  mounted tree, credential-shaped flags and values refused.
- `network.py` screens an endpoint with `netguard` and pins the address it screened, so a
  rebinding answer cannot redirect a request; plaintext HTTP is loopback-only.
- `transport.py` launches one contained process per operation through bubblewrap
  (`--unshare-all`, no host network) with `prlimit`/`systemd-run` limits, and builds the HTTP
  client over the pinned transport.
- `discovery.py` normalises an untrusted catalog: bounded sizes, samples stripped, uncertifiable
  schemas kept but marked unsupported, duplicate names refused, annotations kept as evidence only.
- `persistence.py` stores definitions, catalogs and grants, invalidating grants whose schema
  changed and withdrawing authority when a definition changes.
- `tool.py` is the adapter that makes an MCP tool an ordinary `Tool`.

Schema v85 (`src/hutch/mcp_schema.py`) adds `mcp_servers`, `integration_tool_catalog` and an
`operation_class` grant column defaulting to `unknown`.

### 2.3 Product surface (commits `5db63320`, `97d2b121`)

- `/connectors` (`src/hutch/server/connectors_page.py`, `templates/connectors.html`) installs,
  tests, reviews, grants and revokes with plain CSRF-protected forms. It is in the sidebar next
  to Models, in both the server nav model and the SPA, and in the command palette.
- `src/hutch/readiness.py` reports each assistant's connector tools with their effect class, and
  names connectors installed but not granted to it.
- `src/hutch/server/mcp_api.py` exposes the same operations as JSON, local-owner only.

### 2.4 Documentation and site (commits `826609bf`, `473edc04`, `5dd3d067`, `7d1cf1b7`)

`docs/connectors.md` is the operator guide; `docs/connections.md`, `docs/architecture.md` and
ADR-0017 carry dated corrections. The site has a connectors section whose claims document
(`docs/marketing-site.md`) states what it may and may not say.

### 2.5 Live validation against a real third-party server

`mcp-server-time==2025.9.25` from PyPI, installed in its own virtual environment, registered
through the review path, discovered (2 tools), granted one, and called successfully through the
sandbox. An ungranted tool was absent from the built tool set, and a call with arguments the
server's own schema rejects was refused before dispatch. Evidence in
`artifacts/third-party-live-validation.json`, run by `live_validate_third_party.py`.

The install also produced a real instance of the compatibility failure class the research
predicted: the server is built against SDK 1.x and cannot import against the pinned 2.x. Details
in `validation.md` section 6.

### 2.6 Skills that require a connector tool

A skill may now declare `mcp__<integration>__<tool>` in `hutch.requires-tools`. The check reads
the connector grant as well as the Bot's allowlist, the runtime and the readiness report share
one implementation (`src/hutch/skill_requirements.py`), a missing connector tool reports its own
code and names Connectors, and a Strict Offline Bot cannot satisfy the requirement because its
worker has no host network.

### 2.7 Fixes from independent review (commit `64c63561`)

A read-only review found four guarantees that existed only in prose. All four are fixed and
tested: the effect receipt for non-read calls, per-call approval despite a standing allow, the
effect class re-checked after a re-classification and after the approval wait, and credential
hygiene in argv and in literal definition values.

### 2.8 Skill update review

An update is a write path. `skill_update.compare_packages` compares the installed package with the staged one and
reports what applying would change: new or dropped `requires-tools` and `requires-connections`, a
changed `allowed-tools` declaration, an instruction edit with byte counts, and files added,
removed or modified by sha256. Differences that alter what the skill requires are collected as
material and lead the summary, because that is the difference between reviewing and
rubber-stamping. `src/hutch/skill_update.py`; exposed as `staged_changes` on the skill detail and
rendered first in the inspector's staged block.

### 2.9 Skill dependencies

`hutch.requires-skills` lets one procedure declare that it builds on another. A dependency is
satisfied only when the named skill is installed, reviewed, enabled and assigned to the same Bot,
which mirrors what the loader checks. It reports `requires_skills` and names the dependency and
the missing state. The tool, connection and skill checks now live in one function
(`skill_requirements.binding_problem`) with a fixed reporting order, and `skills.py` got shorter
rather than longer. The check is one level deep by design, pinned by a test.

### 2.10 Failure legibility

Discovery against an origin that answers HTTP but is not an MCP server raised the SDK's protocol
exception with no handler, so testing a connector with a wrong URL returned a 500. It now returns
409 with one sentence naming the stage: no answer within the deadline, an answer that is not MCP,
or an unreachable host. The server's own text is discarded, because a response body is untrusted
input, and no catalog is recorded.

### 2.11 Skill content review

Structural checks prove what a package is; they say nothing about what it asks a model to do.
`src/hutch/skill_scan.py` reviews the content and reports: invisible or reordering characters
(format characters, the Unicode tag block, bidi overrides) with their code points escaped so a
reviewer can see what a model would read; language that changes what the assistant may do rather
than describing a procedure; credential-location references; bundled programs, reported as inert
because Hutch never runs them; and instruction files too large for their description to represent.

The report is advisory in both directions, and the wording says so: a finding does not block trust,
and a clean scan is not an endorsement. Findings appear in the inspector before trust and as
`scan` on the skill detail.

### 2.12 Installing a skill from a URL

`src/hutch/skill_remote.py` fetches a published package and installs it untrusted, with its
provenance recorded: requested URL, final URL after redirects, host, archive digest, size and fetch
time. The fetch goes through `netguard`, so a private address or a redirect to one is refused before
a body is read. Archives are inspected in memory against an 8 MiB download budget, a 64 MiB
expansion budget and a 16 MiB per-member budget, and every member is written through a path check
so nothing can escape the staging directory. Re-fetching over an existing install requires an
explicit `replace`, and the install path writes `trust: null` for any new bytes: arriving over the
network is not review, and anyone can publish a new version at the same URL.

### 2.13 Published registries

A registry is a JSON document at an https URL (`hutch.skill-index/1`) that lists packages. Hutch
reads configured indexes, valides every field, and shows what is listed. Nothing installs because a
registry exists, and nothing is trusted because it was listed.

Integrity is a digest pin, stated precisely: when an entry publishes `sha256`, the downloaded
package must match or the install is refused, which protects against a package being swapped after
publication. It does not prove authorship and does not defend against a malicious index. Hutch does
not verify signatures, and no surveyed platform documents an interoperable format.

A failed index falls back to the last saved listing with its read time, so an outage is not
rendered as "nothing published". `src/hutch/skill_registry_index.py`, exposed through the skills API
and a panel in the skills view.

### 2.14 Skill dependency resolution

`hutch.requires-skills` refusal now has a route: the dependency report names each missing dependency
and whether a configured registry lists it, with version, publisher and digest. Bounded to three
levels, and a cycle is reported rather than chased. It is a report, never an installer.
`src/hutch/skill_dependency.py`.

## 3. Skills and plugins

Not delivered in this pass, and the reason is a real dependency rather than an omission:

- **Skills**: the module already covered far more of the brief than it assumed. `skills.py`
  implements discovery, install, content hashing, trust, per-assistant assignment, run-level
  activation, staged updates with `apply_update` re-hashing the staged bytes, rollback,
  disablement, uninstall, version/license/compatibility metadata, declared tool and connection
  requirements, and readiness reporting for all of it. Three gaps were real and are closed:
  skills could not require an MCP tool (2.6), an update could not say what differed (2.8), and a
  skill could not depend on another skill (2.9). Content review (2.11) and URL installation with
  provenance (2.12) close the two gaps that were about a package arriving from somewhere the owner
  did not prepare. Still not implemented, each for a stated reason: a browsable marketplace (a
  product decision with trust and moderation consequences, and the brief forbids turning Hutch into
  a generic package manager without demonstrated need), skill-to-skill dependency *resolution* (the
  declarations are checked; nothing installs a dependency for you), and package signing (no surveyed
  platform documents verifying skill signatures, so there is no format to interoperate with).

- **Plugins: a decision, not a deferral.** No plugin runtime is built, and that is the answer
  rather than a gap. Consider what a plugin would have to contribute:

  * connectors: already a reviewed definition, installed and granted through the connector plane;
  * skills: already a reviewed package with content review and staged updates;
  * tool definitions: already connector tools, or a first-party tool, which is a code change;
  * executable code: the only thing none of the above covers, and the one thing the research
    found every surveyed platform has paid for with containment and permission bugs.

  So a plugin would either bundle reviewable material that already has its own review path, or it
  would execute third-party code. The first adds a second install path over the same material,
  which `AGENTS.md` forbids ("no second registry, no duplicated enforcement") and which would let a
  bundle's provenance stand in for review the owner never did. The second has no demonstrated need
  and no proposed containment that the connector sandbox does not already provide to a program the
  owner named explicitly.

  If a bundle ever is justified, the shape that fits this architecture is already clear: a manifest
  that names connector definitions and skill packages, validated against the schemas that exist, and
  installed as *staged references* that each still go through their own review. That is a small
  addition to what is here, and it must not become a way to skip a review step. Nothing in this
  delivery claims plugin support.

## 4. Verification

See `validation.md` in this directory for exact commands, results and the live-validation labels.

## 5. Known limitations

- One third-party MCP server has been exercised end to end (`mcp-server-time`). General
  third-party compatibility is not claimed: a server built against a different SDK generation
  needs its own pinned environment, as `validation.md` section 6 records.
- One real public HTTPS origin has been contacted through the pinned transport. No connector has
  been run against a real third-party MCP *service*: bearer acceptance, cross-origin redirects and
  provider rate limiting are unobserved.
- The skill update review, dependency resolution and registry catalogue are covered by tests and, for the registry, an API round trip; none has a recorded browser journey
  with a real staged update.
- The remote HTTP transport has unit coverage of endpoint screening and pinning, and no live
  endpoint has been contacted.
- OAuth for MCP endpoints is not implemented; only `none` and a bearer token from an environment
  variable.
- Resources and prompts are not exposed; only tools.
- The `/connectors` page has no recorded browser journey or screenshot review. It is exercised
  through the test client only.
- The SPA does not render connector state; the page and the API are the surfaces.

## 6. Commits

| Commit | Contents |
|---|---|
| `826609bf` | Primary-source research (14 sources, 7 failure reports) |
| `934e1b69` | Dispatch-level grant and schema enforcement; artifact module split |
| `fd3002a4` | Governed MCP client plane, schema v85, API, containment tests |
| `5db63320` | `/connectors` page, nav, palette, page tests |
| `97d2b121` | Connector access and absence in assistant readiness |
| `473edc04` | Operator guide, ADR/architecture corrections, state-machine fix |
| `5dd3d067` | Guide reconciled with the page and readiness reporting |
| `7d1cf1b7` | Marketing site connectors section and claims rules |
| `931dce63` | Restore the work a stale-tree commit reverted |
| `ddff52ce` | Skill content review and URL installation with provenance |
| `38d93281` | Record the plugin decision |
| (this pass) | Registries with digest pinning, dependency resolution, bearer validation |
| `64c63561` | Review findings fixed and covered by tests |
| (carried by `a4b2377f`) | Skills resolve connector grants; third-party live validation |
| `663828fd` | Streamable HTTP live validation; pinned-origin rule tested |
| `3d849cd6` | Skill update review: what applying a staged update changes |
| `1c188851` | Skill dependencies, and one home for the requirement vocabulary |
| `02a08e55` | A connector that answers but is not an MCP server reports why |
