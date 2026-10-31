# Connector plane: validation record

Date: 2026-10-30. Every command below was run in this checkout. Nothing here is a projection.

## 1. Labels used

- **Automated, offline**: a pytest run with no network and no provider.
- **Real process, sandboxed**: the repository's own MCP fixture server launched through the real
  bubblewrap launcher, spoken to over the real SDK.
- **Visually inspected**: a screenshot I opened and looked at, not just a test assertion.
- **Blocked**: could not be attempted here, with the reason.
- **Not tested**: possible, simply not done.

## 2. Focused suites

| Command | Result |
|---|---|
| `uv run --frozen --no-sync pytest -q tests/test_mcp_guarantees.py` | 12 passed |
| `... tests/test_mcp_plane.py` | 29 passed |
| `... tests/test_mcp_transport.py` | 2 passed (both real-process, sandboxed) |
| `... tests/test_mcp_api.py` | 8 passed (5 real-process) |
| `... tests/test_connectors_page.py` | 6 passed (3 real-process) |
| `... tests/test_integration_dispatch.py` | 10 passed |
| `... tests/test_migration.py` | 41 passed |
| `... tests/test_runtime_builtin.py tests/test_integration_dispatch.py tests/test_integration_catalog.py tests/test_integration_contract_regressions.py` | 110 passed, 3 xfailed |
| `... tests/test_api.py` | 49 passed |
| `... tests/test_templates.py tests/test_navbar_consistency.py tests/test_studio_shell.py` | 52 passed, 1 skipped |
| `... tests/test_ui_vocabulary.py tests/test_site_tokens.py tests/test_claims.py` | 153 passed, 1 skipped |
| `npm run check:agent` | context hygiene, tool contracts, constitution and agent map all pass |

## 3. Full offline suite

Command, with scratch moved off the 12 GB `/tmp` tmpfs:

```
env TMPDIR=$HOME/.hutch-tmp/pytest-full-run \
  uv run --frozen --no-sync pytest -q --no-header --tb=no --ignore=tests/e2e
```

Result: **4687 passed, 10 failed, 63 skipped, 3 xfailed, 2 errors in 2707.93s**.

An earlier attempt without `TMPDIR` produced 103 failures and 245 errors; the repo's own
`docs/agent-workflow.md` names the cause (scratch exhaustion). `scripts/prune_validation_tmp.py`
freed 14.82 GiB, and the disk-backed run then passed 4687 tests that the tmpfs run could not.

Attribution of the ten remaining failures:

| Test | Cause |
|---|---|
| `test_tool_catalog_lazy::test_build_tools_instantiates_only_granted_catalog_tools` | **This work.** `construct_mcp_tools` read `bot.id` from a stub Bot. Fixed by returning no tools for a Bot without an id; the test passes. |
| `test_emoji_audit::test_repository_is_emoji_clean` | **This work.** The research note quoted a GitHub label containing an emoji. Removed; the audit passes. |
| `test_routes::test_a_default_that_cannot_run_is_refused` | Not this work. It asserts a 422 for `opencode/opencode/big-pickle`; the route-problem behaviour is another lane's uncommitted change in `src/hutch/route_problem.py` and `src/hutch/server/app.py`. |
| `test_remote_pairing::test_local_cli_launch_ignores_inherited_remote_enable_switch`, `...::test_remote_cli_flag_sets_internal_switch_after_configuration_validation` | Not this work. Both fail on `[Errno 98] address already in use: ('127.0.0.1', 8787)`; a `hutch serve` started at 21:14 (before this session) holds that port. |
| `test_native_containment::test_no_ipv4_ipv6_dns_or_host_unix_socket`, `test_store_events::test_batched_writer_sustains_over_1000_events_per_second`, `test_worker::test_a_worker_that_ignores_stop_is_escalated_to_sigkill`, `test_workflow_api::test_amendment_drain_refuses_tool_enabled_child_without_stop_side_effect`, `test_workflow_api::test_amendment_preview_does_not_reuse_results_derived_from_effects_or_evidence` | Load-sensitive. Each passes in isolation on this tree, under contention-heavy parallel work from other lanes. Recorded as flaky here, not as passing coverage. |

So: two failures were mine and are fixed; the rest are attributed above and none of them touches
the connector code.

## 4. Live validation

| Capability | Label | Evidence or reason |
|---|---|---|
| **Third-party MCP server, discovery and call** | **Real provider, live** | `live_validate_third_party.py` installs `mcp-server-time==2025.9.25` from PyPI into its own virtual environment, registers it through the real service layer, discovers 2 tools, grants one to an assistant, and calls it. The call returned a real timezone record: `{"timezone": "Europe/London", "datetime": "2026-10-31T10:45:33+00:00", "day_of_week": "Saturday", "is_dst": false}`. Evidence: `artifacts/third-party-live-validation.json` |
| Third-party schema enforced before dispatch | **Real provider, live** | Calling the granted tool with `{"nonsense": 1}` was refused with `missing required argument 'timezone'. Nothing was run.` The schema that refused it is the one the server published, not a Hutch guess |
| Ungranted third-party tool unreachable | **Real provider, live** | `mcp__time__convert_time` was absent from the built tool set entirely and refused as an unknown tool, even though the server advertises it |
| Local stdio connector, discovery and call | **Real process, sandboxed** | `test_mcp_transport.py` launches the fixture through `stdio_launch_argv`, pages its catalog, calls a granted tool, and the child reports its own environment and network state |
| Sandbox containment of a connector | **Real process, sandboxed** | The child reports `secret_env: null` (Hutch's environment is not inherited), `home: /tmp/hutch-home`, `network: isolated` |
| Install, test, grant, revoke, remove over HTTP | **Real process, sandboxed** | `test_mcp_api.py`, `test_connectors_page.py` |
| **Remote Streamable HTTP connector** | **Real server, live (loopback)** | `live_validate_http.py` starts an MCP server on loopback with the SDK's Streamable HTTP transport, registers it as a connector, discovers 2 tools and calls one, which returned real structured output. Evidence: `artifacts/http-live-validation.json` |
| Private-address and scheme screening | **Automated, offline, with a live-address check** | The live run refused `mcp.example.com` resolving to `10.1.2.3` before anything started. Two tests prove the pinned transport refuses an unreviewed loopback origin and a non-TLS public endpoint |
| **Public HTTPS through the pinned transport** | **Real public origin, live** | `live_validate_public_https.py` screens `https://example.com/mcp`, completes a real TLS request through `PinnedMcpHTTPTransport` (200, 577 bytes), and shows that pointing a connector at an origin with no MCP endpoint fails as a bounded connector error rather than a hang or a crash. Evidence: `artifacts/public-https-live-validation.json` |
| **Bearer authentication** | **Real server, live (loopback, authenticating)** | `live_validate_bearer.py` runs an MCP server that requires an exact bearer token. Unset variable: refused, naming the variable. Correct token: discovery and a call succeed, and the server recorded the header it received. Wrong token: refused, with the token absent from the message. Evidence: `artifacts/bearer-live-validation.json` |
| **Cross-origin redirect refusal** | **Real server, live** | The same run points a connector at a local server that answers every request with a 307 to a second local origin. The redirector saw the request and the **target received zero requests**: a redirect to an origin the owner did not review is not followed |
| A connector against a real third-party MCP service | **Not tested** | No public MCP server and no credential were available. A third-party service accepting a token, and provider rate limiting, have not been observed |
| Third-party MCP server | **Real provider, live** | See above: `mcp-server-time` from PyPI, installed and called through the sandbox. Only this one server has been exercised; general third-party compatibility is not claimed |
| OAuth for a connector endpoint | **Blocked, not implemented** | Only `none` and a bearer token from an environment variable exist |
| Approval on a non-read connector call | **Automated, offline, with a real approval gate** | `test_mcp_guarantees.py` raises a real approval card in a worker thread, resolves it, and asserts the transport was reached only after approval |
| Revocation mid-run | **Automated, offline** | `test_integration_dispatch.py::test_revocation_takes_effect_on_the_next_call_without_rebuilding_tools` |

## 5. Visual validation

Method: a disposable dashboard (`HUTCH_STATE_DIR` under `~/.hutch-tmp`, port 8792) seeded with
real store rows through `seed_visual_state.py`: one local connector tested and granted to two
assistants with three different effect classes, and one connector merely installed. No invented
UI state; the connector is the same fixture server used by the tests.

Captured at 1440x960, 900x1024, 390x844 and 320x844, plus a keyboard pass. Measurements at every
viewport: no horizontal overflow, no clipped controls, no interactive target under 32 px, no
console errors, and a visible 2 px focus ring on the first tab stop. Screenshots are in
`artifacts/connectors-page/`.

I inspected each capture. Four defects were found by looking and fixed:

1. **Fields overlapped their labels.** The first version nested help text inside `<label>`, which
   the shared form macros explicitly forbid. Rewritten to use `_form.html` macros
   (`hutch-field` / `hutch-label` / `hutch-input` / `hutch-help`).
2. **The tool name was printed twice** (title fell back to the server name and both were shown).
3. **"Allow" and "Effect" collided** in the tool row. The controls are now a compact inline group
   and the select carries an accessible name instead of a visible duplicate label.
4. **The layout CSS was in the wrong stylesheet.** The page loads `hutch-forms.css`, not
   `style.css`, so the first fix had no effect until it moved.

Not verified: a screen-reader run, 200 percent text scaling, and touch interaction on a physical
device. Keyboard reach and focus visibility were checked, not full screen-reader semantics.

## 6. A real compatibility finding

Installing the official time server produced the failure class the research predicted, and the
research note now has a live instance of it rather than a citation. `mcp-server-time==2025.9.25`
imports `McpError` from `mcp.shared.exceptions`; the pinned SDK 2.x renamed it `MCPError`. With
the SDK resolved normally, the server dies at import:

```
ImportError: cannot import name 'McpError' from 'mcp.shared.exceptions'
```

That is not a Hutch bug and Hutch cannot paper over it: an MCP server built against SDK 1.x needs
SDK 1.x in *its own* environment. The working definition therefore pins the server's dependencies
in an isolated virtual environment and mounts that tree read-only, which is what an operator has
to do today. Two consequences worth stating plainly:

- A connector definition that "works" can still fail after a package update moves its SDK, which
  is why the definition fingerprint covers the executable and every reviewed mount. A changed
  package tree is refused until the owner reviews it again.
- The failure is legible. Discovery reported the transport failure as a connector configuration
  error, not as an empty tool list, so an owner sees "this did not start" rather than "this has no
  tools".

Hutch does not attempt to install a server's dependencies, and this record does not claim
otherwise.

## 7. Skills that require a connector tool

A skill can now declare a connector tool in `hutch.requires-tools`, and the check reads the
connector grant rather than the Bot's allowlist. The tests are in
`tests/test_skill_connector_requirements.py` (7 cases: ungranted, granted, native still native,
runtime and readiness agree, readiness names Connectors, granted makes the skill ready, Strict
Offline withholds). Verified by those tests; not exercised end to end with a real model run.

## 8. What the public-origin run found

The first public-HTTPS run exposed a defect rather than confirming one. Discovery against an
origin that answers HTTP but is not an MCP server raised the SDK's protocol exception, and no
route caught it, so `POST /api/v1/integrations/{id}/test` would have returned a 500 for an
ordinary operator mistake: a wrong URL.

Discovery now translates the whole failure class into one sentence that names the stage, with the
server's own text discarded because a response body is untrusted input:

```
the endpoint answered, but not as an MCP server; check the URL path and whether it needs authentication
```

Three shapes are distinguished because the fix differs: no answer within the deadline, an answer
that is not MCP, and an unreachable host. The API returns 409 with that sentence, the connector
stays merely installed, and no catalog is recorded. Two tests cover it: one at the service layer
asserting the server's text is not forwarded, one over HTTP asserting 409 rather than 500.

## 9. Skills: content review and URL install

Both are covered by tests, not by a live third-party source.

- Content review (`tests/test_skill_scan.py`, 22 cases) covers each finding class, one finding per
  phrase family, the tag-block and bidi characters specifically, the finding cap, ordering, and the
  two properties that matter most: **a finding does not block trust**, and **a clean scan does not
  stand in for trust**.
- URL install (`tests/test_skill_remote.py`, 16 cases) drives the real `netguard` fetch path with
  an injected resolver and transport, the same seam the netguard suite uses. It covers a working
  install with provenance, a single-file package, refusal of a private address, refusal to follow a
  redirect to a link-local address, an HTTP error, an archive member that escapes the package, an
  absolute member path, a package with no `SKILL.md`, an empty download, and a compression bomb
  that fits the download budget but not the expansion budget. Two cases pin the trust semantics:
  replacement requires `replace`, and a replacement never inherits the previous review.

No package was fetched from a real public host: the suites use an in-process server and a fixed
resolver, and no third-party skill package was reviewed. The egress rules themselves are the ones
`tests/test_netguard.py` already exercises against DNS rebinding and redirect targets.

## 10. What the bearer run found

The first bearer run failed, and the failure was in Hutch: `open_client` built an `Authorization`
mapping from the connector's `from_env` reference and then never passed it to the HTTP client, so
every bearer connector would have connected unauthenticated and been refused with a message
blaming the URL. The unit tests could not see it because nothing had ever asserted that a server
received the header.

The fix passes the headers to the client, and two regression tests now cover the boundary: a
missing variable is refused by name, and a real loopback server records `Bearer <token>` while the
raised refusal contains no part of the token.

## 11. Registries and dependency resolution

Both are covered offline, against a mocked transport, with the real `netguard` screening in place:

- `tests/test_skill_registry.py` (29 cases): index format and field validation, refusal of a
  non-https package URL and a malformed digest, duplicate handling within and across registries,
  the entry cap, merging order, fallback to the last saved listing when a registry fails, refusal
  of a registry that resolves to a private address, digest verification (match, mismatch, and no
  digest published), refusal of an unlisted name, and the dependency report including a cycle.
- The mocked transport routes by `Host` rather than by connection URL, because `netguard` dials the
  validated address: the numeric address in the request URL is itself evidence the pinning works.

No real public registry was contacted. The index format is Hutch's own, and publishing one is a
documented JSON shape rather than an established ecosystem standard.

## 12. What this record does not claim

No third-party service was contacted. No connector was installed from a registry or marketplace,
because none exists here. Nothing in this delivery is a live-provider acceptance result.
