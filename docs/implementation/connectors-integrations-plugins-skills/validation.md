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
| Local stdio connector, discovery and call | **Real process, sandboxed** | `test_mcp_transport.py` launches the fixture through `stdio_launch_argv`, pages its catalog, calls a granted tool, and the child reports its own environment and network state |
| Sandbox containment of a connector | **Real process, sandboxed** | The child reports `secret_env: null` (Hutch's environment is not inherited), `home: /tmp/hutch-home`, `network: isolated` |
| Install, test, grant, revoke, remove over HTTP | **Real process, sandboxed** | `test_mcp_api.py`, `test_connectors_page.py` |
| Remote Streamable HTTP connector | **Not tested against a live endpoint** | Endpoint screening and address pinning are unit-covered with injected resolvers; no real endpoint or credential was available, so no TLS handshake, bearer acceptance, redirect or DNS answer has been observed |
| Third-party MCP server | **Blocked** | No third-party server was installed on this host. Every connector test uses `tests/fixtures/mcp_stdio_server.py` |
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

## 6. What this record does not claim

No third-party service was contacted. No connector was installed from a registry or marketplace,
because none exists here. Nothing in this delivery is a live-provider acceptance result.
