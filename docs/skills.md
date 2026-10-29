# Skills

A **skill** is a reusable instruction package: a directory containing `SKILL.md`: YAML frontmatter
(`name`, `description`, and optional fields) plus Markdown instructions, following the
[Agent Skills specification](https://agentskills.io/specification). Skills carry *knowledge and
procedure*, not authority. They cannot add tools, accounts, budgets, or approval overrides; every
action a skill's text suggests still goes through the Bot's policy, approvals, and sandbox.

Three different things are deliberately kept apart:

| | What it is | Where it lives |
|---|---|---|
| **Installation** | Reviewed bytes copied under Hutch's state directory with a content hash | `~/.local/state/hutch/skills/` |
| **Trust** | An operator decision recorded against one exact hash | `skills/registry.json` |
| **Assignment** | A Bot's saved reference to a skill name | the Bot document (`skills` field) |
| **Activation** | Loading one skill's instructions for one run | the run record (`skill_activation`) |

Only trusted, enabled skills are disclosed to a model or can be activated. Installation alone
changes nothing.

## Lifecycle

```
discover/import → validate → review/trust → install/version → assign to Bots → activate
→ inspect → update/rollback → disable/uninstall
```

* **Discover**: Hutch scans deliberately selected locations (below). Discovered packages are
  candidates; they are never loaded automatically. Invalid packages stay visible with the exact
  reason instead of disappearing.
* **Import**: copy a local folder, or install a bundled sample. Imports are inert until reviewed.
* **Validate**: the parser is lenient about cosmetics (name/directory mismatch, oversized
  description) and strict about identity (no safe `name`, no `description`, unparseable YAML,
  duplicate keys, oversized body). Every finding is a diagnostic with a level.
* **Review/trust**: the operator sees provenance, license, hash, resources, declared
  prerequisites, the full instructions, and every diagnostic, then trusts that exact hash.
* **Assign**: a Bot may reference up to 20 installed, trusted skills. The reference is saved in
  the Bot document; the runtime re-checks trust, enablement, and the package hash at every run
  start.
* **Activate**: an operator can activate assigned skills for one run from the composer (or
  `hutch run --skill`, or the `skills` field of the run API). The model can also load an assigned
  skill on demand with the `use_skill` tool.
* **Update**: `update` stages a new version from the skill's recorded source. The reviewed
  version stays active and keeps running until the operator applies the update; the inspector shows
  the staged instructions so "review the update" is literal. Applying re-reads and re-hashes the
  staged bytes and refuses if they changed after staging. `discard` drops the staged version;
  `rollback` restores the previous retained version (the last 3 are kept).
* **Disable/uninstall**: disabling stops future disclosure and activation immediately, even
  though earlier instructions may remain in an old transcript. Uninstalling removes the files;
  Bots that reference it show a visible "not installed" readiness reason rather than failing
  silently.

A package that changes on disk after review is detected by full hash at the enforcement points:
run start, `use_skill` body/resource loads, trust, recheck, and the inspector (which always reads
the bytes it shows). The compact library card uses a cheap file-count/size/mtime signature and may
briefly keep showing the previous state for an edit that preserves all three: the run path still
withholds it. A trusted package whose bytes changed is withheld from runs and reported as
**Changed on disk** until the operator re-reviews it; `recheck` never re-trusts content on its own.

## Where skills are discovered

| Scope | Locations (in precedence order) |
|---|---|
| Project (a Bot's folder workspace) | `<folder>/.hutch/skills/`, `<folder>/.agents/skills/`, `<folder>/.claude/skills/` |
| User | `~/.hutch/skills/`, `~/.agents/skills/`, `~/.claude/skills/` |
| Bundled | the samples shipped with Hutch |

Project skills shadow user skills, which shadow bundled samples. Every shadowed duplicate is
listed with its winner; nothing is replaced silently. Scanning is bounded (500 directories per
root), reads only direct child directories containing `SKILL.md`, skips symlinked entries, and
never walks arbitrary home directories.

`~/.claude/skills` is included as a deliberate compatibility location because many existing
skills are installed there; it is read, never written.

## What the model sees (progressive disclosure)

1. **Catalog**: assigned, trusted, enabled skills are listed by name and description in the
   system prompt (~50–100 tokens each). Nothing else is loaded.
2. **Instructions**: a skill's full body is loaded either because the operator activated it for
   the run (frozen into the run's system prompt) or because the model called
   `use_skill(name)` (returned as a tool result with an untrusted-content label and a hash).
3. **Resources**: bundled files are listed, not read. `use_skill(name, resource="…")` reads one
   file, confined to the skill directory, capped at 64 KiB, UTF-8 only, and hash-verified against
   the run's resolved package so a file changed mid-run is never served.

Skill text is instruction material, not permission. The activation result explicitly says so, and
the system prompt states that skills cannot grant tools, accounts, budgets, or approval bypasses.
`allowed-tools` frontmatter is shown to the operator and never converted into an authority grant.

## Runtime support

| Runtime | Skills |
|---|---|
| Built-in | Full support: catalog, `use_skill`, explicit activation, run snapshot |
| Pi / OpenCode | **Not supported.** Bound skills are listed in the run log as not loaded; explicitly activating a skill fails the run before it starts rather than silently ignoring the request |

## Readiness

`GET /api/v1/bots/{ref}/readiness` (also shown in each Bot's Skills panel) reports separate areas:
runtime, model, tools, skills, connections, with a status per item. `missing` blocks the
configured workflow; `warning` is a visible, explained capability loss that does not block the
rest. Readiness never calls a provider.

A skill can additionally declare prerequisites in its namespaced metadata:

```yaml
metadata:
  hutch.version: "1.0"
  hutch.requires-tools: "files, shell"            # tools/groups the Bot must enable
  hutch.requires-connections: "outlook-mail"      # account prerequisites from a fixed vocabulary
```

Declared tools that the Bot does not enable, and declared connections that are not granted, keep
the skill out of the run with the exact reason in readiness and the run log.

## CLI

```bash
hutch skills list                       # installed + discovered candidates + collisions
hutch skills validate ./my-skill        # diagnostics without installing
hutch skills install --builtin workspace-summary
hutch skills install ./my-skill
hutch skills show workspace-summary     # review state, source, hash, resources, assigned Bots
hutch skills trust workspace-summary    # record review of the exact bytes; enables it
hutch skills disable workspace-summary  # stop future disclosure/activation
hutch skills enable workspace-summary
hutch skills update workspace-summary   # stage from the recorded source
hutch skills apply-update workspace-summary
hutch skills discard-update workspace-summary
hutch skills rollback workspace-summary
hutch skills uninstall workspace-summary --yes

hutch bot create my-bot --model ollama/llama3.2 --skills workspace-summary
hutch bot update my-bot --skills ""     # clear assignments
hutch run my-bot "summarize the folder" --skill workspace-summary
```

## API

```
GET    /api/v1/skills                          library: installed, available, collisions, scan notes
GET    /api/v1/skills/{name}                   detail incl. instructions, resources, diagnostics, bound Bots
POST   /api/v1/skills/install                  {source: "builtin"|"path", name|path}
POST   /api/v1/skills/{name}/trust|enable|disable|recheck
POST   /api/v1/skills/{name}/update            stage
POST   /api/v1/skills/{name}/update/apply      make the reviewed update active
POST   /api/v1/skills/{name}/update/discard
POST   /api/v1/skills/{name}/rollback
DELETE /api/v1/skills/{name}                   uninstall
GET    /api/v1/bots/{ref}/readiness            shared readiness resolver
```

Bots accept `skills` in create and patch. Run submission accepts `skills` (explicit activation) on
`POST /api/v1/tasks/runs` and on conversation messages; the value is validated against the Bot's
assignments and current trust state, and recorded on the run as `skill_activation`. Paired phones
cannot manage skills or activate them (owner action).

## Security model

* Installation rejects symlinked packages and entries, path escapes, files over 2 MB, packages
  over 20 MB, and packages over 2,000 files. Frontmatter is parsed with YAML aliases/anchors
  rejected before construction (an alias graph could otherwise explode when rendered), metadata
  values must be scalars, and prompt catalog text is escaped so a description cannot close the
  surrounding block.
* The registry is written atomically with `0600` permissions and a cross-process file lock;
  concurrent mutations serialize instead of racing.
* Resource reads are canonicalized and confined to the reviewed package directory.
* Skill content is treated as untrusted input at every step: it is wrapped with a
  non-permission label, scripts are never executed automatically, and running one requires the
  ordinary shell tool under the Bot's policy and approvals.
* Revocation takes effect at the next enforcement boundary: a run whose explicitly activated
  skill was disabled, uninstalled, or modified between submission and start **fails before
  starting** with the reason; assigned-only skills are excluded with a run-log warning.
* Nothing in this subsystem fetches skills from the network, extracts archives, runs installation
  hooks, or installs dependencies. Remote registries and marketplaces are not supported.

## Bundled samples

| Skill | What it does | Prerequisites |
|---|---|---|
| `workspace-summary` | Digest of the Bot's workspace folder | files tool |
| `repo-review` | Read-only Git repository review | shell + files tools, a Git workspace |
| `outlook-mail-digest` | Digest of recent Outlook mail | an Outlook Mail connection granted to the Bot |

Samples ship inside the package and are installed from the local copy; they are not fetched.

## Limits

| Bound | Value |
|---|---|
| Skills per Bot | 20 |
| Instructions body | 100 KB (warning above 50 KB) |
| Total activated body per run | 150,000 characters |
| Package size / files / single file | 20 MB / 2,000 / 2 MB |
| Discovery directories per root | 500 |
| Retained versions per skill | 3 |
| Resource read | 64 KB, UTF-8 text only |

## Not supported (stated honestly)

* External runtimes (Pi, OpenCode) do not load Hutch skills.
* No remote/archive import, no marketplace, no automatic update checks.
* No keyword matching or hidden auto-activation: activation is either operator-selected or an
  explicit `use_skill` tool call.
* Skill instructions are not re-injected into older conversations; activation is per run. A
  follow-up message needs its own activation.
