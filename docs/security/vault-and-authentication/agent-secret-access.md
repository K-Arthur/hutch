# Agent access to credentials

The rule this programme is built around:

> An agent may *use* a credential. It may not *read* one, and it may not read one by accident.

That rule is implemented as three mechanisms. Two are done; the third is designed and permissioned
but not wired.

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

## 3. Mediated use — not done

`VaultBook.resolve_for_use(ref, principal, destination=...)` exists, checks the grant, decrypts and
records the use with a destination hostname. **Nothing calls it yet.**

Until a tool or connector calls it, `use` returns a value into the calling process just as `reveal`
does. The difference is who is allowed to ask and what the audit says — not whether the value stays
inside the vault. Saying otherwise would be a claim without a mechanism.

### What completing this requires

1. A tool that accepts a `SecretRef` instead of a literal value, with the schema validating the
   reference grammar before dispatch.
2. A mediator per integration that applies the value at the network boundary: an `Authorization`
   header, an OAuth token exchange. The mediator must never return the value in a tool result.
3. A test that runs a real agent turn with an injected instruction ("print the API key") and asserts
   the tool result, transcript and event log contain no secret, while the mediated operation succeeds.

### What it must not become

A proxy that any subprocess can bypass. If an agent can call `curl` directly with a credential it can
read, a proxy does not help. Process isolation is a prerequisite, and this programme does not claim
it.

## Prompt injection

The threat that matters most. The mitigations that are real today:

- Injected content cannot extract a value from a tool result, because no tool returns one.
- It cannot read metadata it has no grant for, and a denied read is visible in the audit.
- It cannot widen a grant; only the owner can change grants, and that check is server-side.

The mitigation that is not real yet: a bot that reads a plaintext key file with a shell tool. That is
the gap the migration in `migration.md` exists to close.
