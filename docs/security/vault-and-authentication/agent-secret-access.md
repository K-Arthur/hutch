# Agent access to credentials

The rule this programme is built around:

> An agent may *use* a credential. It may not *read* one, and it may not read one by accident.

That rule is implemented as three mechanisms, each with a test that fails if it regresses. The third
(mediated use) is complete for HTTP requests; `security-limitations.md` §3 states exactly how far it
reaches and where it does not.

## 1. A value is never in agent context — done

There is no path from the vault to the model. Specifically:

- `SecretMetadata` has no value field (`test_vault_integrity.py` asserts this).
- The API's list, detail, create and update responses carry metadata only; only
  `POST /api/v1/vault/secrets/{id}/reveal` returns a value, and it is audited as `reveal`.
- `UsableSecret.__repr__` and `__str__` are redacted, so a log line, an f-string or a traceback does
  not print a credential.
- The audit table's `reason` is a closed vocabulary, so an exception message cannot smuggle a value
  into a durable row.
- Tests assert the value is absent from the database files, the events/runs/messages tables and the
  log.

What this does **not** protect against: a bot with a shell tool reading a plaintext credential that
is still stored outside the vault (model API keys, ChatGPT tokens — see `current-state.md` §8). Those
are not migrated yet, and no claim is made that they are.

## 2. Access is granted, scoped and audited — done

- Deny by default. A principal with no row in `vault_grants` is refused, and the refusal is a durable
  audit row with `outcome=denied`, `reason=no_grant`.
- Scope is a second, independent check. A grant cannot let one bot reach another bot's secret.
- Revocation is immediate. There is no in-memory grant cache.
- `use` and `reveal` are different permissions and different audit actions, so "an agent used a
  credential" is never indistinguishable from "a person read a credential".

## 3. Mediated use — done for one egress shape

The chain is: `vault_http_request` (tool) → policy → approval gate → `vault.egress.mediate_http` →
`VaultBook.resolve_for_use` → `safehttp.safe_request`.

Each link enforces one thing, and none of them relies on another doing it by accident:

- **The tool** accepts only an opaque reference. Its JSON Schema pins the reference grammar
  (`^secret://hutch/local/sec_[0-9a-f]{24}(#v\d+)?$`) and has no field that could carry a value, so
  the model has nothing to put a key into.
- **Policy** screens the URL before the vault is opened: scheme, credentials, internal names, every
  IP-literal spelling. A private target fails here, whatever the grant says.
- **The approval gate** raises the same style of detail a person reviews: destination, method,
  header, reference. The detail has no value in it, which the ask-mode test asserts.
- **`mediate_http`** refuses a header name Hutch sets, refuses a prefix that could split a header,
  refuses a non-ASCII credential rather than mangling it, and rejects a body on `GET`/`HEAD`.
- **`resolve_for_use`** checks the grant, then the destination binding, then decrypts. A grant with
  no binding is `denied/no_destination` in the audit, not a success.
- **`safe_request`** pins the connection to an address `resolve_public` approved, keeps `Host` and
  SNI on the requested name, applies `Host` last so a caller cannot override it, and does not follow
  redirects. A 3xx comes back as the result.

Three properties are enforced rather than described:

1. **A credential cannot be walked to a new host.** Redirects are not followed, so a compromised or
   honest-to-a-fault service returns 302 and the next request needs its own authorization.
2. **A service cannot echo the credential back into context.** The response body and headers are
   scrubbed of the exact value, and `set-cookie`/`authorization` response headers are dropped.
3. **The value is not persisted.** `test_vault_http_tool.py` scans `events`, `runs`, `messages` and
   `tool_actions` after a real dispatch; `test_vault_agent_turn.py` runs the real engine with a
   runtime that prints the whole tool result and claims the injected instruction asked for the key.
   The run succeeds, the request arrives with the right header, and the value is in no table.

### What it must not become, and has not become

This is not a proxy any subprocess is forced through. A bot with `shell` can still make its own
requests; if it also has `reveal` it can read the value and do as it likes. Mediated use narrows the
path it provides. It does not close a path the agent already has, and it is not claimed to. See
`security-limitations.md` §3.

## Prompt injection

The threat that matters most. The mitigations that are real today:

- Injected content cannot extract a value from a tool result, because no tool returns one.
- It cannot read metadata it has no grant for, and a denied read is visible in the audit.
- It cannot widen a grant; only the owner can change grants, and that check is server-side.

The mitigation that is not real yet: a bot that reads a plaintext key file with a shell tool. That is
the gap the migration in `migration.md` exists to close. A bot holding `reveal` is also a bot that
can be talked into printing a value; mediated use is the path that does not require that grant.
