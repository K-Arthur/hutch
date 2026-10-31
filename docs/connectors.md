# Connectors: governed MCP servers

A connector is a third-party MCP (Model Context Protocol) server that Hutch calls as a tool
source. Hutch is the client. For a local server it launches one contained process per
operation; for a remote server it speaks Streamable HTTP to one reviewed endpoint. In both
cases it reads the server's tool list, stores what it found, and exposes only the tools an
assistant was explicitly granted.

The implementation is `src/hutch/integrations/mcp/`, the storage is schema v85, and the design
record is [ADR-0017](adr/0017-governed-mcp-integration-plane-and-context-scaffolding.md). The
ecosystem research that shaped the review model is
[research/2026-10-connectors-ecosystem/research.md](research/2026-10-connectors-ecosystem/research.md).

The guiding rule is that a definition is review material, not permission. Saving a connector
runs nothing and authorizes nothing. Testing it runs the server once and reads its tool list,
but calls no tool. Authority begins only when a named assistant is granted named tools, and
that authority is re-read before every call.

## Connectors compared with provider connections and skills

| Surface | What it is | What it grants |
|---|---|---|
| Provider connection | A model API endpoint with its own credentials, protocol, billing and allowance. See [Connections](connections.md). | A model route an assistant can be configured to use. It never adds a tool. |
| Connector | An MCP server, local or remote, that supplies tools. Its execution is contained by Hutch. | Named tools on named assistants, bound to a reviewed schema revision. |
| Skill | A package of instructions (`SKILL.md`) that changes what the model is told. See [Skills](skills.md). | No new execution authority. A skill cannot widen tools, files or network reach. |

A connector does not replace the provider conversion layer, the tool registry or the approval
path. A connector tool is an ordinary `Tool` in the one registry, under the canonical name
`mcp__<integration_id>__<server_tool_name>`, and it passes the same approval gate and the same
receipt bracket as a native tool.

Connecting a model provider is therefore not the same act as installing a connector, even when
both appear under Apps & AI. Provider credentials pay for inference. Connector definitions
name a program to run or an endpoint to reach.

## The five states

The consent ladder is defined in `src/hutch/integrations/base.py`. Each state is an independent
gate, and a higher state never implies the ones below it.

| State | What earns it | What it does not do |
|---|---|---|
| `installed` | A definition passed validation and was saved. | The server has not necessarily been started, and nothing is enabled. |
| `reachable` | The transport answered: a local process started, or a remote endpoint responded. | It says nothing about credentials or tools. |
| `authenticated` | The credential the definition references was accepted by the server. | It does not authorize any operation. |
| `capabilities_discovered` | A bounded `tools/list` result was read, normalized and stored, with at least one supported tool. | A catalog entry is review material, not authority. |
| `operation_authorized` | At least one assistant holds at least one grant on this connector. | It authorizes only the named tools on the named assistants. |

What the connector operations write today: a saved definition is `installed`; a successful test
writes `capabilities_discovered` when the server returned any tool (including tools Hutch then
marks unsupported, because the diagnostics are the review material), or `reachable` when the
server answered with an empty list; the first grant writes `operation_authorized`; revoking the
last grant returns the connector to `capabilities_discovered` and disables it. No operation
writes `authenticated`: a bearer token is presented when the client connects, so a successful
list already proves it was accepted, and the state column keeps the value for connections that
can test credentials separately.

Installing and testing never run a tool, and a discovered tool is never enabled by discovery
alone. Nothing defaults on.

## Installing a local (stdio) server

A local definition names an executable, its argv, the read-only trees the server may read, and
environment entries. This is the shape the validator accepts:

```json
{
  "transport": "mcp_stdio",
  "command": "/usr/bin/python3",
  "args": ["/home/you/connectors/acme/server.py", "--config", "/home/you/connectors/acme/config.json"],
  "read_only_paths": ["/home/you/connectors/acme"],
  "env": {
    "ACME_LOG_LEVEL": "info",
    "ACME_API_TOKEN": {"from_env": "ACME_API_TOKEN"}
  }
}
```

The fields that exist are `transport`, `command`, `args`, `read_only_paths` and `env`. Anything
else is refused; there is no timeout field, no `cwd` field, no shell wrapper and no header list.

- `transport`: `mcp_stdio`.
- `command`: an absolute path to an executable file. It is resolved with `realpath` and must
  exist, be a regular file and be executable.
- `args`: a list of at most 64 strings, each at most 4,096 characters and containing no NUL.
  The combined arguments must stay within 32 KiB.
- `read_only_paths`: at most 16 absolute host paths, each mounted read-only at the same path
  inside the sandbox.
- `env`: at most 32 entries. The name must match `^[A-Z_][A-Z0-9_]{0,63}$`. The value is either
  a plain string or `{"from_env": "NAME"}`, which stores a reference and resolves it when the
  process starts.

### What the validator enforces

These rules are in `src/hutch/integrations/mcp/config.py` and are enforced by the API, not by
the interface:

- **bubblewrap must exist.** Without `bwrap`, local connectors cannot be saved at all.
- **The executable must be in a trusted place.** It must live under `/usr`, `/bin`, `/sbin`,
  `/lib` or `/lib64`, or inside one of the definition's own read-only paths. A program sitting
  in the run workspace or in an unreviewed home directory is refused.
- **A command is never a shell string.** There is no shell, no glob expansion and no argument
  interpolation. The argv list is executed directly.
- **Credential-shaped arguments are refused.** An argument that starts with `-` and whose flag
  name (the text after the dashes, before any `=`) normalizes to contain `token`, `secret`,
  `password`, `apikey`, `clientsecret`, `authorization`, `cookie`, `credential` or `privatekey`
  is refused outright. `--api-key=abc123` and `--token-file /path` are both refused. A
  positional value is not screened, which is why the referenced environment variable is the
  only supported place for a credential: it never reaches SQLite, a transcript or a log.
- **Credential-shaped environment names must be references.** `ACME_API_TOKEN:
  {"from_env": "ACME_API_TOKEN"}` is accepted. `ACME_API_TOKEN: "literal-value"` is refused with
  the instruction to use `from_env`. A non-credential literal such as `ACME_LOG_LEVEL: "info"`
  is accepted, and must be a single line with no NUL under 4,096 characters.
- **Mounts are screened against credential boundaries.** A read-only path must be absolute and
  exist. It cannot be `/` or `/home`; it cannot be under `/etc`, `/var`, `/proc`, `/dev`,
  `/run`, `/root` or `/sys`; it cannot be a system root such as `/usr`; it cannot be your home
  directory or an ancestor of it; it cannot be another user's home; it cannot be Hutch's state
  directory or an ancestor of it; it cannot overlap another mount in the same definition; and it
  cannot overlap the assistant's writable run workspace. The shell sandbox's extra mount screen
  runs over it as well.
- **Fingerprints pin the program.** Saving computes `command_sha256` (the executable's bytes)
  and `read_only_fingerprints` (a per-tree sha256 that records relative paths, file modes and
  symlink targets without following them). Both are stored with the definition. Every launch
  recomputes them and refuses on a mismatch, and saving a definition over an existing connector
  compares them too: "the local MCP executable changed since review" or "reviewed server files
  changed since approval". A package that changed on disk must be reviewed again.
- **A definition change is a new consent.** The definition revision is the sha256 of the
  normalized, non-secret definition. When it changes, the stored catalog and every grant are
  deleted and the connector returns to `installed` and disabled. That covers a new executable,
  a new mount, new arguments, a new endpoint URL and a new auth reference.

### The sandbox the server runs in

A local server is third-party code, so Hutch runs it the way it runs a shell command: inside the
same bubblewrap containment, with no ambient credentials, no host network, no writable host path
other than one workspace, and resource limits enforced by `prlimit` and `systemd-run`.

- The process is created per operation and ended before the call returns. A revoked grant
  therefore means a stopped server, by construction, rather than a pooled child that outlives
  its run.
- Namespaces: `--unshare-all`, `/usr` read-only, a private `/proc` and `/dev`, tmpfs `/tmp` and
  `/run`.
- The run workspace is bound read-write at **`/workspace`**, which is the working directory.
  `HOME` is `/tmp/hutch-home`. `PATH` is `/usr/local/bin:/usr/bin:/bin`. `LANG` and `LC_ALL` are
  `C.UTF-8`, `TERM` is `dumb`, `TMPDIR` is `/tmp`.
- The environment is cleared. The child inherits nothing from Hutch's own environment, and only
  the `env` entries the owner reviewed are set, with references resolved at spawn time.
- Server stderr is discarded. It never becomes run output.
- Limits: `systemd-run --user --scope` with `MemoryMax=512M` and `TasksMax=32`, and `prlimit`
  with 120 seconds of CPU, a 64 MiB file size, 128 open files, 512 MiB of address space and no
  core dumps.

Because the sandbox is a separate filesystem view, every path a server is given must be a
sandbox path. The workspace exists as `/workspace`, a reviewed read-only path keeps its host
path, and nothing else on the host is visible. A definition whose `args` name a host path
outside those trees fails at launch rather than falling back to an unsandboxed run, and a tool
argument that names such a path fails inside the server. During a test the workspace is an
empty, disposable scratch directory under `<state>/mcp-scratch/`, also mounted at `/workspace`,
so a server that needs its own data files must read them from a reviewed read-only path.

## Installing a remote (HTTP) endpoint

```json
{
  "transport": "mcp_http",
  "url": "https://mcp.acme.example/mcp",
  "auth": {"type": "bearer", "from_env": "ACME_MCP_TOKEN"}
}
```

The fields that exist are `transport`, `url` and `auth`.

- `url`: HTTP or HTTPS only, with no username, password, query string or fragment, and a port
  between 1 and 65535. HTTPS is required for every non-loopback host. Plaintext HTTP is accepted
  only when the host is `localhost`, `localhost.localdomain`, or a loopback IP address.
- `auth`: `{"type": "none"}` (the default when the field is absent) or
  `{"type": "bearer", "from_env": "NAME"}`, where `NAME` matches the environment-name pattern.
  There is no header map, no basic auth and no OAuth grant type. A bearer token is read from the
  Hutch process environment when the connection opens and is sent as an `Authorization` header;
  a missing or empty variable fails closed before any request is made.

Endpoint screening and pinning are in `src/hutch/integrations/mcp/network.py`:

- The saved endpoint is validated again at every connection: the hostname is resolved, a
  non-local endpoint must be HTTPS, the URL must pass netguard's screen, and every resolved
  address must pass the blocked-address screen. A local endpoint must resolve only to loopback
  and must match the reviewed origin exactly, so a reviewed `http://127.0.0.1:8765/mcp` cannot
  be reused to reach another local port.
- The address that was screened is the address actually dialled. A connection that was not
  pinned for the current request is refused, so a DNS answer that changes between the check and
  the connect cannot redirect the request.
- Unix sockets are refused. Redirects are not followed. Proxy environment variables are ignored.
- Each origin keeps its own connection pool, so two hostnames that share an address cannot share
  one connection. TLS verification and the `Host` header still use the hostname.
- Server-Sent Events are capped at 1 MiB per event.

## Testing a connector

Testing is `POST /api/v1/integrations/{integration_id}/test`. It starts the server once (or
opens the endpoint), reads the tool list with pagination of up to 20 pages, normalizes it,
stores the catalog and stops the process. **It reads the tool list only. It never calls a
tool.** A test that called tools would be an unapproved side effect behind a button labelled
"test".

The response reports `tool_count`, the names invalidated by this refresh, and the stored
catalog. The catalog review in `src/hutch/integrations/mcp/discovery.py` applies these rules:

- At most 200 tools. Duplicate server tool names, or names that collide after namespacing,
  refuse the whole catalog and leave the previously stored one unchanged.
- The exposed name is `mcp__<integration_id>__<server_tool_name>`. Server names must be 1 to
  128 characters with no control characters.
- A title longer than 256 characters or a description longer than 4,096 characters is dropped
  and recorded as a diagnostic.
- The tool's metadata record (name, title, description, input schema, output schema,
  annotations) is measured as canonical JSON. Above 64 KiB the tool is stored as unsupported
  with empty schemas.
- `default`, `example`, `examples` and `$comment` are stripped from the schema, so a server's
  sample value is never mistaken for an argument the model supplied. Non-finite numbers are
  refused.
- The input schema root must declare `type: object`. `$ref` is unsupported. Every keyword
  Hutch's validator cannot certify becomes a diagnostic, for example "keyword 'x' is not
  checked by this validator" or "schema nesting exceeds 32 levels". At most 8 diagnostics are
  kept.
- A tool with any diagnostic is stored as `supported: false` and cannot be granted.
- Server annotations such as `readOnlyHint` and `destructiveHint` are stored as display
  evidence only. They never classify or authorize a tool: a connector is not read-only because
  its server says so.

Each tool's `schema_revision` is the sha256 of its name, title, description, input schema,
output schema and annotations. That digest is what a grant is bound to.

## Granting tools to assistants

A grant names one assistant, one or more tools from the stored catalog, an operation class per
tool, and the connector revision the owner reviewed:

```json
{
  "bot": "reader-assistant",
  "tools": ["read_workspace", "search"],
  "operation_classes": {"read_workspace": "read", "search": "read"},
  "revision": "<the connector's current revision>"
}
```

- `revision` must equal the connector's current definition revision. A mismatch is refused with
  "this connector changed; discover and review its tools again", so a grant is always written
  against the definition the owner saw.
- Every named tool must exist in the stored catalog and be supported. A tool outside the
  catalog is refused, and so is a tool with diagnostics.
- `bot` accepts the assistant id or its name. A grant for an unknown assistant is refused.
- Granting replaces that assistant's grant set for that connector: the previous rows are deleted
  in the same transaction. Granting twice does not add to the first set.
- Strict Offline assistants are refused ("Strict Offline assistants cannot use external
  connectors") and receive no connector tools even if a grant row existed.

### Operation classes

The class is the owner's classification of the tool's effect. It is stored on the grant and it
decides whether a call asks first.

| Class | Behaviour |
|---|---|
| `read` | Runs without an approval. It is the only class that may run silently. |
| `write` | A fresh approval on every call, including in automatic approval mode. |
| `destructive` | A fresh approval on every call, recorded as an outward action. |
| `unknown` | A fresh approval on every call. This is the default when no class is supplied. |

`unknown` is deliberately the default: a pre-existing grant whose class is unknown after the
schema v85 migration asks every time. The class is never inferred from server annotations, and
an unrecognized class value for a granted tool is refused at write time.

### What a call does

1. Dispatch re-reads the grant before the call runs (`src/hutch/runtime/dispatch.py`). This check
   happens before schema validation, so a revoked grant never leaks whether the arguments would
   have matched. A refusal reads "`mcp__acme__search` is no longer granted to this assistant for
   that connection; nothing was run."
2. The adapter re-reads the grant row and compares its schema revision with the revision it was
   constructed from. A mismatch refuses: "The connector's tool definition changed since it was
   reviewed".
3. Arguments are validated against the stored input schema before anything is sent. A failure
   says the connector rejected the arguments before sending.
4. A rehearsal (`dry-run`) returns a simulated result and sends nothing.
5. For `write`, `destructive` and `unknown`, the approval card shows the connector, tool, account
   label, arguments and effect class. After the decision the grant is read a second time, so a
   revocation while the card is open wins over the approval.
6. One operation, with a 60 second deadline. The process or connection is ended before the call
   returns.
7. The result is bounded at 256 KiB. Structured content and text are kept; image, audio,
   resource and resource-link blocks are replaced with a placeholder. A server `isError` is a
   failure. A result that asks for follow-up input is refused, because Hutch does not grant a
   connector prompt extra authority. A transport failure is reported as "nothing is confirmed
   to have happened" and is not retried automatically.

A read-class call leaves no effect receipt. A `write`, `destructive` or `unknown` call is
bracketed by an intent and a receipt, with effect `process` for stdio and `web` for HTTP, and the
recorded arguments include the connector id and the server tool name.

## Revocation, removal and schema changes

**Revoking one assistant** is `DELETE /api/v1/integrations/{integration_id}/grants/{bot}`. It
takes effect on the next tool call, not the next run: dispatch reads the grant from the store
before every call and never caches it. Other assistants keep their grants. When the last grant
for a connector is revoked, the connector is disabled and returns to
`capabilities_discovered`.

**Removing a connector** is `DELETE /api/v1/integrations/{integration_id}`. It removes the
definition, the stored catalog and every assistant grant in one transaction. Re-adding the same
integration id starts at `installed`, disabled, with no catalog and no grants. This is the
uninstall-without-revocation failure the research ledger records elsewhere, closed here by
construction.

**Changing a definition** deletes the catalog and every grant and disables the connector. A new
executable, a changed mount, new arguments, a new URL or a different auth reference are all new
things to consent to, and the review state restarts.

**When a server changes a tool**, the next test recomputes each tool's schema revision. Grants
for a tool whose revision changed, or for a tool that no longer exists, are deleted; grants for
unchanged tools survive. The same comparison runs at execution, so a stale tool object fails
instead of running against a schema nobody reviewed. A description edit counts as a change,
because the description is part of the record the owner reviewed.

**When the program changes on disk**, the fingerprints no longer match and the definition cannot
be saved or launched until it is reviewed again. This covers a replaced executable and any file
inside a mounted read-only tree.

## The HTTP API

All connector routes live in `src/hutch/server/mcp_api.py` and are local-owner only. None of
them appear in the paired-phone route inventory, so a paired phone receives 403. Every response
is sent with `Cache-Control: no-store`. A refusal is a 409 carrying the service's own sentence,
never a generic failure.

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/api/v1/integrations` | List configured connectors with tool and grant counts. |
| `POST` | `/api/v1/integrations` | Validate and save a definition. |
| `GET` | `/api/v1/integrations/{integration_id}` | One connector with its catalog, grants and public definition. |
| `POST` | `/api/v1/integrations/{integration_id}/test` | Run the server once, read the catalog, store it. |
| `POST` | `/api/v1/integrations/{integration_id}/grants` | Grant tools to one assistant. |
| `DELETE` | `/api/v1/integrations/{integration_id}/grants/{bot}` | Revoke one assistant's grants. |
| `DELETE` | `/api/v1/integrations/{integration_id}` | Remove the connector and everything derived from it. |

### GET /api/v1/integrations

```json
{
  "connectors": [
    {
      "integration_id": "acme",
      "title": "Acme",
      "transport": "mcp_stdio",
      "state": "capabilities_discovered",
      "enabled": false,
      "revision": "<definition sha256>",
      "tool_count": 4,
      "grant_count": 0
    }
  ],
  "detail": "Each connector is installed here, tested here, and then granted to named assistants. Installing and testing never run a tool; nothing is authorized until you grant it."
}
```

### POST /api/v1/integrations

Request:

```json
{"integration_id": "acme", "title": "Acme", "definition": {"transport": "mcp_stdio", "command": "/usr/bin/python3", "args": ["/home/you/connectors/acme/server.py"], "read_only_paths": ["/home/you/connectors/acme"]}}
```

Response 200:

```json
{"integration_id": "acme", "revision": "<definition sha256>", "invalidated": false, "definition": {"transport": "mcp_stdio", "...": "the normalized definition"}}
```

An id that is not a lowercase slug starting with a letter is a 400. A validation refusal is a
409 with the validator's sentence, for example "credential values and credential-like command
flags cannot be stored in a server definition".

### GET /api/v1/integrations/{integration_id}

Response 200 carries `integration_id`, `title`, `state`, `enabled`, `transport`, `revision`,
`definition`, `catalog` and `grants`. The definition shown here omits `command_sha256` and
`read_only_fingerprints`, and environment entries appear as `env:NAME` for a reference or
`literal:value` for a reviewed literal. Each catalog entry carries `server_tool_name`,
`canonical_name`, `schema_revision`, `title`, `description`, `input_schema`, `output_schema`,
`annotations`, `supported` and `diagnostics`. Each grant carries `bot_id`, `bot_name`,
`server_tool_name`, `canonical_name` and `operation_class`. An unknown connector is a 404.

### POST /api/v1/integrations/{integration_id}/test

No request body. Response 200:

```json
{"integration_id": "acme", "tool_count": 4, "invalidated": [], "catalog": ["...catalog entries..."], "detail": "Testing reads the connector's tool list only. It never calls a tool."}
```

A connector with no saved definition is a 409 ("configure the connector before testing it"), and
a catalog the normalizer refuses is a 409 prefixed "the connector's tool catalog was refused:".

### POST /api/v1/integrations/{integration_id}/grants

Request body as shown in the granting section. Response 200:
`{"integration_id": "acme", "bot_id": "<assistant id>", "tools": ["read_workspace", "search"]}`.
An unknown tool, an unsupported tool, a stale revision, an unknown assistant or an offline
assistant is a 409.

### DELETE /api/v1/integrations/{integration_id}/grants/{bot}

Response 200:

```json
{"integration_id": "acme", "bot_id": "<assistant id>", "remaining_grants": 1, "detail": "Revocation applies to the next tool call, not the next run."}
```

`remaining_grants` counts every remaining grant on the connector, across assistants. An unknown
assistant is a 409.

### DELETE /api/v1/integrations/{integration_id}

Response 200:

```json
{"integration_id": "acme", "removed": true, "detail": "The definition, its catalog and every assistant grant were removed."}
```

An unknown connector is a 404.

## Troubleshooting

**"local MCP servers need bubblewrap; install bwrap to enable them"**
`bwrap` is not installed, so no local definition can be saved. Install bubblewrap. There is no
unsandboxed fallback.

**"local MCP processes need Hutch's Linux sandbox: ..."**
The host cannot sandbox. The reason names the missing piece: bubblewrap, `prlimit` (util-linux)
or `systemd-run` is absent, or bubblewrap cannot create a sandbox here (usually a container
without the needed privileges). Connectors need the same Linux sandbox as the shell tool.

**"the configured Linux process-containment tools are unavailable"**
The sandbox probe passed but one of `bwrap`, `prlimit` and `systemd-run` disappeared from
`PATH` for the Hutch process. Check the service unit's environment.

**"a local systemd user session is required to launch a contained MCP process"**
The Hutch process has no `DBUS_SESSION_BUS_ADDRESS` and `XDG_RUNTIME_DIR`, which `systemd-run
--user` needs. Start Hutch inside a user systemd session (a desktop login, a user service, or
`systemctl --user`), not from a bare supervisor without a session bus.

**"the credential variable NAME is not set; set it before starting this server"**
The `from_env` variable is missing or empty in the environment of the Hutch process, not in your
interactive shell. Export it where Hutch starts, then restart the service. The same message
appears for a bearer endpoint as "set it before connecting". The value is never stored.

**A server that writes a banner to stdout**
stdout is the JSON-RPC channel. A banner, log line or progress dot on stdout is a protocol
violation, so testing the connector fails instead of showing a tool list. Write diagnostics to
stderr, which Hutch discards. This is a server-side fix; there is no tolerance setting.

**A tool reported as unsupported**
The catalog entry has `supported: false` and a `diagnostics` list. Common entries: "input schema
root must declare type: object", "$ref is unsupported; tool schemas cannot load external or
unresolved references", "keyword 'x' is not checked by this validator", "tool schema metadata
exceeds the 64 KiB review limit". An unsupported tool cannot be granted. Publish a bounded
object schema, or leave that tool ungranted.

**"`mcp__acme__search` is no longer granted to this assistant for that connection"**
The grant was revoked, invalidated by a catalog refresh, or deleted with the connector. Nothing
ran. Test the connector, check that the tool still exists and is supported, then grant it again.

**"The connector's tool definition changed since it was reviewed"**
The tool's schema revision moved after the assistant's tools were built. Refresh the catalog
with a test and grant the tool again.

**"this connector changed; discover and review its tools again"**
The definition revision no longer matches the revision in the grant request. A save with new
material deletes the catalog, so test before granting.

**"plaintext HTTP is only accepted for a loopback MCP endpoint"** or **"Remote MCP endpoints
require HTTPS"**
Use HTTPS for a remote endpoint. Plain HTTP is limited to `localhost` and loopback addresses.

**"MCP server processes are not available inside Strict Offline runs"**
The calling run is Strict Offline, which has no host network and no connector processes. Use an
assistant that is not Strict Offline, and remember that Strict Offline assistants cannot be
granted connector tools at all.

**"the executable must be under /usr or inside one of the reviewed read-only paths"**
Move the program under a system root or add its directory to `read_only_paths`.

**"the assistant's run workspace is unavailable"**
The run has no usable workspace directory. This is a runtime problem rather than a connector
one; check that the run workspace exists and is a directory.

## Limits

| Limit | Value | Where it applies |
|---|---|---|
| Tools per catalog | 200 | A larger `tools/list` refuses the catalog. The discovery loop also stops after 20 pages. |
| Tool metadata record | 64 KiB | Canonical JSON of name, title, description, input schema, output schema and annotations. Above it the tool is unsupported. |
| Tool description | 4,096 characters | Longer descriptions are dropped with a diagnostic. |
| Tool title | 256 characters | Longer titles are dropped with a diagnostic. |
| Server annotations | 8 KiB | Larger annotation objects are discarded with a diagnostic. |
| Diagnostics per tool | 8 | Further diagnostics are dropped. |
| Tool result | 256 KiB | Longer output is clipped and marked as clipped. |
| One operation | 60 seconds | Wall clock for a single tool call. |
| Read timeout | 20 seconds | Per request handed to the MCP client and the HTTP client. |
| Discovery | 45 seconds | Wall clock for reading a full catalog. |
| Reviewed package | 128 MiB | Total bytes of one read-only mount tree, and of the executable itself. |
| Arguments | 32 KiB | Combined UTF-8 size of `args`. At most 64 arguments of 4,096 characters each. |
| Read-only mounts | 16 per definition | More is refused. |
| Environment entries | 32 per definition | More is refused. |
| SSE event | 1 MiB | Larger server-sent events are refused by the HTTP client. |
| Server memory | 512 MiB | `MemoryMax` for the contained process. |
| Server tasks | 32 | `TasksMax` for the contained process. |
| Server CPU | 120 seconds | `prlimit --cpu` for the contained process. |

## Not verified

- **No real third-party MCP server has been exercised on this host.** The transport and API
  tests launch `tests/fixtures/mcp_stdio_server.py`, a small JSON-RPC server written for the
  test suite, through the real sandbox. No vendor server, package or published server
  implementation was installed or run.
- **The remote HTTP transport has not been run against a live endpoint.** Its screening,
  pinning and refusal paths are unit-tested with a stub resolver, but no real HTTPS MCP server
  has been contacted, no TLS handshake with a third-party endpoint has been observed, and no
  bearer credential has been accepted by a real service. DNS, proxies, certificate rotation and
  provider rate limits are unmeasured here.
- **No interface exists yet.** The connector routes are served, but the dashboard has no screen
  that calls them; the API is the only surface. There is no connector discovery directory, no
  registry integration and no package installation from a catalog.
- **OAuth for MCP endpoints is not implemented.** Only `none` and a bearer token read from an
  environment variable are supported.
- **Resources and prompts are not supported.** Only tools are discovered and called. Server
  instructions, resource templates and prompt endpoints are ignored.
- **Third-party behaviour under load is unmeasured:** pagination beyond 20 pages, cancellation
  during a long tool call, servers that change their catalog mid-session, and servers that rely
  on sampling or roots. Hutch refuses a follow-up-input request rather than answering it.
