# Hutch documentation

This directory is the public documentation tree for Hutch, a local-first, MIT-licensed
multi-bot platform in development preview. Start with the repository
[README](../README.md) for the product overview. Development setup is in
[CONTRIBUTING.md](../CONTRIBUTING.md), vulnerability reporting is in
[SECURITY.md](../SECURITY.md), and community expectations are in
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md).

Some documents here are current guides. Others are dated records kept for traceability.
Where a document and the running code disagree, the code and the current
[evidence ledger](realignment/ledger.md) win.

## Start here

| Document | Contents |
|---|---|
| [Architecture](architecture.md) | component map, storage schema, control plane and concurrency model |
| [Safety model](safety.md) | deny/ask/allow rules, approval flow and honest limits |
| [Operating Hutch locally](operations.md) | Linux service setup, sandbox requirements, backups, restore and phone supervision |
| [Bot configuration](bot-config.md) | bot fields, model specs, schedules, limits, YAML preview and reviewed import |
| [Models](models.md) | chat model switcher, fit, model slots, prices and `hutch doctor` |
| [Connections](connections.md) | provider plans, keys, OAuth app connections, unsupported integrations and limits |
| [Runtime setup](runtime-setup.md) | prerequisites for OpenCode, Ollama and other optional runtimes |
| [Marketing site claims](marketing-site.md) | claim and evidence rules for the static site |
| [Brand assets](brand-assets.md) | third-party service marks, Hutch identity assets and typefaces |

## Capabilities and behavior

| Document | Contents |
|---|---|
| [Requirements](requirements.md) | product requirements v0.2 and implementation status |
| [Roadmap](roadmap.md) | product scope and phased direction |
| [Dynamic workflows](workflows.md) | saved, reviewable multi-step plans |
| [Skills](skills.md) | Agent Skills `SKILL.md` packages: trust, assignment and limits |
| [Grounding](grounding.md) | live search and media checks, timestamps and source handling |
| [File formats](file-formats.md) | document and media capability matrix and limits |
| [Response style](response-style.md) | wording, depth and humor controls |
| [Templates](templates.md) | starter assistant configurations |
| [Channels](channels.md) | Telegram channels and their current limits |
| [Computer use](computer-use.md) | supervised browser and desktop operation |
| [Performance](performance.md) | measured baselines on one machine, not guarantees |
| [Validation queue](validation-queue.md) | opt-in machine-wide admission queue |

## Design

| Document | Contents |
|---|---|
| [Design system](design-system.md) | shared tokens, components, icon policy and accessibility rules |

## Research and evidence

| Location | Contents |
|---|---|
| [research/](research/) | dated research notes and reference reviews, including incident-based requirements and runtime comparisons |
| [realignment/](realignment/) | continuation ledger, measured baseline, evidence ledger and dated validation records |
| [realignment/artifacts/](realignment/artifacts/) | captured screenshots, manifests and machine-readable validation evidence |
| [adr/](adr/) | numbered architecture decision records |
| [qa/](qa/) | interface QA review and images |
| [prompts/](prompts/) | dated implementation prompts and reports kept for traceability |

`docs/realignment/` holds dated evidence artifacts, not current product documentation. Files
there record what was measured on a given date; some paths, screenshots and conclusions are
historical and may not match the current code. Link to them as evidence, not as a statement
of current behavior. The ledger files are maintained on an ongoing basis; individual dated
reports are not.

## Working on the repository

| Document | Contents |
|---|---|
| [Agent workflow](agent-workflow.md) | repository-context rules and seam rules for agent sessions |
| [Repository hygiene](repository-hygiene.md) | ignore rules, package selection and local commit checks |
| [Concurrent agents](concurrent-agents.md) | worktree operating model for parallel sessions |
| [Commit attribution](commit-attribution-policy.md) | commit authorship policy |
