# Unified tool-calling: plan, contracts, evidence

Status: implementation in progress on `toolcall/unified` (branch off `main` @ c869a5a).
This document is the bounded plan + evidence ledger for the unified tool-calling
compatibility layer. It is updated as slices land; "implemented" does not mean
"verified" unless a check is listed under validation.

## 1. Revalidated root causes (working checkout, 2026-10-10)

The inspected `main` leads are re-checked against `c869a5a`:

| Lead | Current state | Response |
|---|---|---|
| `Tool.spec()` emits the wire envelope directly | Still true (`tools/base.py`), but the registry is small and stable | Introduce a canonical `ToolDefinition` snapshot + per-protocol serialization; do not mutate `parameters` in place |
| `_client()`/`execute()` submit `tools` through one OpenAI-shaped path | True (`runtime/builtin.py` builds `ChatRequest.tools` once; providers convert) | Add a compilation step before the loop; keep the OpenAI-shaped request as one wire adapter |
| Malformed JSON replaced with `{}` before dispatch | Invalid JSON is already rejected (`toolrepair.validate_args` + loop rejection), but an **absent or empty** argument body still becomes `{}` and can execute for tools whose schema has no required fields | Distinguish absent/empty argument bodies; reject when the canonical schema requires any property; strict-decode JSON (duplicate keys, `NaN`, `Infinity`, trailing data) |
| `choices[0]` only; absence of `tool_calls` = final text | True in `providers/openai_compat.py`. Also: the flat llama.cpp shape (`tool_calls[].name`/`.arguments`, no `function` envelope, no `id`, `finish_reason: "tool"`) is **not handled** today | Native adapter fixes: tolerant call shapes, synthesized per-response unique call IDs, stream name-merge rules, `"tool"` finish reason |
| Clipped text-only results | True (tool output clipped to per-tool limit; artifacts preserved) | Keep; add structured result envelope + correlated ordering in the loop and prompt/constrained history |
| Fake-client happy paths | `tests/test_providers.py` + `tests/test_runtime_builtin.py` cover the mainstream shapes | Add conformance corpus: schema round-trip, stream differential, adversarial malformed output, per-strategy same catalog |

## 2. Evidence ledger

Legend — evidence: documented / advertised / probed / observed / stale / unsupported.
"Reporter" findings are labeled; maintainer-confirmed findings are distinct.

| # | Source (date checked) | Finding | Evidence | Relevance → design response | Regression test |
|---|---|---|---|---|---|
| E1 | [ollama#11662](https://github.com/ollama/ollama/issues/11662) (fetched 2026-10-10; opened 2025-08-05, still open) | qwen3:32b sometimes emits `{"name": "...","arguments": {...}}` as ordinary **content** instead of `tool_calls`; maintainer reproduced only in the reporter's exact conditions, root cause attributed to model behavior, not a parser bug | reporter + maintainer discussion | Never scan native content for executable calls. Detect the shape and surface a protocol-mismatch diagnostic; do not execute | `test_native_text_looking_like_a_call_is_never_executed` |
| E2 | [vllm#39380](https://github.com/vllm-project/vllm/issues/39380) (fetched 2026-10-10; opened 2026-04-09, closed by author "completed") | gemma4 streaming tool parser inserted `0` after decimal points (`0.45 → 0.045`); maintainer could not reproduce on nightly; author used a local patch | reporter; maintainer unable to reproduce | Our assembler must never reformat numbers; raw text is preserved and re-encoded from the raw string when a call is replayed. Differential stream/non-stream normalization test on the assembler (parser/contract coverage, not a live model repro) | `test_stream_and_nonstream_assemblies_are_equivalent` (numeric corpus) |
| E3 | [vllm#47734](https://github.com/vllm-project/vllm/issues/47734) (fetched 2026-10-10; opened 2026-07-06, fixed by PR #48947 merged 2026-10-06) | Mistral + `tool_choice=required` + streaming produced non-Mistral call IDs; fixed upstream by generating Mistral-format IDs | maintainer-confirmed, fixed | Never assume provider call IDs are unique or any format; synthesize our own fallback IDs unique per response; keep provider ID when present; correlation by exact ID in results | `test_calls_without_ids_get_unique_ids_per_response`, `test_provider_ids_are_preserved` |
| E4 | [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) (fetched 2026-10-10) | Tool definitions: `parameters` JSON Schema; `strict` requires `additionalProperties: false` + all fields required (nullable via `["string","null"]`); Chat Completions is best-effort by default; tool-choice auto/none/required/named | documented | Do not silently rewrite schemas to strict; report strict incompatibilities. Keep best-effort native default | `test_strict_requirements_are_reported_not_rewritten` |
| E5 | [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md) + [GBNF guide](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md) (fetched 2026-10-10) | Server-side tool support requires `--jinja`; generic handler supports all models; `parallel_tool_calls` opt-in; sample response uses top-level `name`/`arguments`, no `id`, `finish_reason: "tool"`. Schema→GBNF: `additionalProperties` defaults to **false** (narrowing!), unsupported keywords silently skipped, cannot mix properties with anyOf/oneOf, nested `$ref` broken, `pattern` must be `^…$`, remote refs not fetched by C++ server | documented | Constrained mode: lowering diagnostics must flag the additionalProperties default and unsupported keywords; root-only discriminated envelope; no remote `$ref` resolution ever | `test_llamacpp_lowering_reports_additional_properties_narrowing` |
| E6 | [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) + [tool calling](https://docs.ollama.com/capabilities/tool-calling) (fetched 2026-10-10) | `format` accepts a JSON Schema (Ollama **Cloud does not support structured outputs**); tool calls arrive as complete objects per chunk; `tool` results are keyed by `tool_name` | documented | Constrained attachment point for native Ollama is the `format` field; cloud-tagged models are ineligible | `test_ollama_constrained_uses_format_field_and_is_cloud_ineligible` |
| E7 | [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/) + [tool calling](https://docs.vllm.ai/en/stable/features/tool_calling/) (fetched 2026-10-10) | `response_format: {type: json_schema, json_schema: {name, schema}}` (guided_* removed in 0.12); strict tool calling with per-tool `strict`, `--tool-strict-level`; required/named always use schema-derived constraints; "validly-parsable, not high-quality" | documented | Constrained attachment on OpenAI-compat surfaces is `response_format`; native best-effort otherwise; do not claim enforcement from advertised support | `test_openai_compat_sends_json_schema_response_format` |
| E8 | [Outlines architecture](https://dottxt-ai.github.io/outlines/main/guide/architecture/) (fetched 2026-10-10) | Only directly steerable models (llama.cpp bindings, MLX, Transformers) get client-side logits processors; server-backed models delegate to provider APIs | documented | Never advertise client-side grammar enforcement against hosted APIs; constrained mode only through the destination server's own controls | `test_constrained_mode_requires_backend_support` |
| E9 | [Anthropic fine-grained tool streaming](https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming) (fetched 2026-10-10) | Opt-in `eager_input_streaming`; `content_block_start` carries placeholder `input: {}`; accumulate `input_json_delta`; parse only at block close; invalid JSON must be returned as an error tool result; `max_tokens` can cut parameters | documented | We do not enable eager streaming; buffered default stays. The SDK assembles; validation on parse. Invalid accumulated JSON is a rejected call, never executed | provider fixture test (SDK path) |
| E10 | [JSON Schema object reference](https://json-schema.org/understanding-json-schema/reference/object) + [jsonschema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/) (fetched 2026-10-10) | A property with `null` is present and fails a `"type": "string"` unless nullable; omission ≠ null; `additionalProperties` defaults to allowed; format checking is opt-in | documented | Canonical validator preserves omission vs null; no permissive coercion of null↔absent; formats checked only where the canonical schema declares them and the dialect requires | `test_omission_and_null_are_distinct` |

## 3. Contracts

New package `src/hutch/toolcalling/` (no inference dependency added):

- `contracts.py` — `ToolDefinition` (name, description, canonical `parameters`, declared dialect,
  schema revision, owner, declared effect class, capabilities, policy metadata, provider alias),
  `Diagnostic`, `CompilationPlan`, `Strategy` (`native`/`constrained`/`prompt`/`disabled`),
  `ActionKind`/`ActionCandidate` (decoded but unvalidated), `ValidatedCall` (canonical, frozen).
- `profiles.py` — `ModelCapabilityProfile` + `Evidence` resolved from provider kind, endpoint class,
  model metadata (digest/template hash where available), and explicit operator override; passive
  observations are inputs, not authority. Unknown components are recorded as unknown.
- `schemas.py` — canonical dialect inventory (2020-12), bounded static analysis (depth, size, refs,
  unions, maps, formats), per-backend lowering with per-field diagnostics classified as
  `equivalent` / `reversibly_encoded` / `locally_enforced` / `narrowed` / `unsupported`.
  No remote `$ref` resolution; no in-place mutation of canonical schemas.
- `compiler.py` — builds and caches immutable `CompilationPlan`s keyed by catalog + profile +
  strategy + compiler version. Compilation never invokes tools, reads credentials, or mutates
  the registry.
- `envelope.py` — versioned bounded action envelope (`hutch-action-v1`) for constrained/prompt
  modes: per-tool branches bound to each tool's own argument schema, plus final/clarify branches.
  Strict whole-message parsing only; no prose scanning.
- `strictjson.py` — strict JSON decoding: rejects duplicate object keys, `NaN`/`Infinity`,
  multiple top-level values, non-object argument bodies.
- `streamassembly.py` — OpenAI-compatible streaming call assembly as an explicit state machine
  (name merge rules, argument accumulation, per-response unique fallback IDs, finish reasons,
  bounds).

Invariants enforced at the loop boundary (see §4 in the assignment): no malformed, incomplete,
unknown, unauthorized, or canonically invalid call reaches execution; no fallback widens
authority; tool results/examples are never executed; a parser badge never substitutes for an
outcome check. Alias mapping is reversible; unknown names are rejected, never fuzzy-matched.

## 4. Supported-mode matrix (initial)

| Route (profile key) | Native | Constrained | Prompt-only | Notes |
|---|---|---|---|---|
| Anthropic Messages | yes (best-effort) | no | explicit opt-in | buffered streaming; strictness not enforced server-side for tools |
| OpenAI Chat Completions | yes (best-effort; `strict` not sent) | not enabled by default | explicit opt-in | strict requirements reported, not rewritten |
| OpenAI Responses (ChatGPT sign-in) | yes | no | explicit opt-in | preview surface |
| Ollama native (local) | yes | `format` schema (`hutch-action-v1`) | explicit opt-in | cloud-tagged models ineligible for constrained |
| llama.cpp server `/v1` | yes when server runs `--jinja` (else probe) | `response_format` json_schema | explicit opt-in | GBNF lowering diagnostics |
| vLLM `/v1` | yes when parser/flags configured (else probe) | `response_format` json_schema | explicit opt-in | strict-tool options documented, not enabled |
| LM Studio / generic OpenAI-compatible | attempted | unknown → opt-in only | explicit opt-in | advertised ≠ verified |
| OpenCode/Pi harnesses | Hutch does not own the loop | — | — | unchanged; fail closed |

`auto` never silently switches strategy mid-run: the plan is chosen per model turn snapshot and
recorded. Prompt-only requires explicit operator policy per Bot; high-consequence approvals
still apply in every mode because all modes converge on the same dispatcher.

## 5. Slices and validation

1. **Strict validation boundary** — strictjson, absent-vs-empty arguments, canonical validation
   wrapper; provider parsing switched; tests for adversarial inputs.
2. **Compiler + profiles** — contracts, schema analysis, plan building, cache; unit + property
   tests; wired into the loop with zero behavior change for native routes.
3. **Native adapter correctness** — llama.cpp flat shape, finish reason `tool`, unique fallback
   IDs, stream name merge; fixture tests.
4. **Constrained backend** — Ollama `format` + OpenAI-compat `response_format`; envelope decode;
   diagnostics; differential tests; explicit failure when the backend criticizes the schema.
5. **Governed prompt fallback** — explicit per-Bot policy, versioned prompt contract, strict
   whole-message parse, bounded repair, no prose scanning; tests that quoted JSON stays inert.
6. **Streaming parity** — streamassembly extraction + byte-split/interleave/duplicate/truncation
   tests; stream vs non-stream differential.
7. **Diagnostics UI** — Tool Compatibility section in Bot settings (design gate: research +
   route approval before implementation).
8. **Docs/packaging/verification** — model setup guidance, safety notes, contributor tests,
   measured overheads, rollback notes.

## 6. Compatibility, migration, rollback

- Default remains native with the existing OpenAI-shaped request; schedules, approvals, budgets,
  and external harnesses are untouched.
- New Bot field (`tool_protocol`, default `auto`) is optional in the JSON `doc` column: no SQL
  migration; legacy bots load unchanged.
- Rollback = revert the branch; no data migrations, no dependency changes required for the
  core path. jsonschema integration is optional (see the validator note) so an install without
  it keeps working with a documented subset validator.
- No credentials, images, or private catalogs are sent during compilation; probes are opt-in,
  bounded, and use ephemeral fake tools only.

## 7. Measured budgets

Measured 2026-10-10 on the development machine (CPython 3.13, bounded validator engine)
with `scripts/toolcalling_bench.py`; no model calls are made by the script.

| Tools | Native compile cold / warm | Constrained compile cold | Native wire tokens | Constrained contract tokens | Envelope bytes |
|---|---|---|---|---|---|
| 1 | 0.11 ms / 0.013 ms | 0.23 ms | 139 | 386 | 852 |
| 10 | 0.44 ms / 0.013 ms | 1.34 ms | 1,382 | 1,474 | 5,433 |
| 100 | 3.57 ms / 0.026 ms | 12.9 ms | 13,841 | 12,387 | 51,243 |

`validate_call` on a representative 4-property schema: ~26 µs. Strict argument decode:
~4 µs. "Warm" means the same live tool instances within a process (identity fast path);
identical catalogs rebuilt in a later run use the content-keyed cache and pay schema
hashing (~3.6 ms at 100 tools). Compilation is well below inference latency at every
size measured, so no validation was loosened to hit a budget. The 100-tool constrained
envelope is ~51 KB of schema: bounded generation with large catalogs costs real
backend grammar-compile time and prompt tokens, which is why scoped tool selection and
two-stage generation remain explicit follow-ups rather than defaults.

## 8. Verification map (evidence → tests)

| Evidence | Regression test |
|---|---|
| E1 Ollama content-channel report | `test_native_mode_content_that_looks_like_an_action_is_flagged_not_executed`, `test_envelope_shaped_tool_output_is_never_executed` |
| E2 vLLM decimal corruption | `test_argument_fragments_reassemble_exactly_at_every_split_point`, `test_numbers_are_never_reformatted_by_the_client`, `test_transcript_normalization_is_equivalent_streamed_and_not` |
| E3 Mistral call-id mismatch | `test_calls_without_provider_ids_get_unique_ids_and_correlated_results`, `test_two_calls_sharing_one_provider_id_are_rejected_without_execution`, `test_conflicting_ids_are_reported_and_the_first_is_kept` |
| E4 OpenAI strict requirements | `test_strict_tool_schemas_are_reported_not_rewritten`, `test_known_profiles_report_states_instead_of_assuming_family_support` |
| E5 llama.cpp GBNF gaps | `test_gbnf_lowering_materializes_additional_properties_and_reports_it`, `test_gbnf_lowering_reports_maps_and_unanchored_patterns_as_local_checks`, `test_cyclic_references_are_refused_for_generation_not_silently_broken` |
| E6 Ollama structured outputs | `test_structured_output_attachment_points_are_per_protocol`, `test_constrained_mode_runs_the_same_canonical_tools_over_the_action_contract`, `test_a_rejected_constrained_schema_fails_clearly_instead_of_downgrading` |
| E7 vLLM structured outputs | `test_structured_output_attachment_points_are_per_protocol` |
| E8 Outlines control boundary | `test_explicitly_unavailable_strategy_refuses_with_the_prerequisite` |
| E9 Anthropic fine-grained streaming | `test_full_response_refusal_and_content_filter_are_typed_not_answers`, strict decode tests |
| E10 presence/null semantics | `test_union_types_and_nulls_follow_json_schema_presence_rules`, `test_annotations_are_ignored_and_defaults_never_become_arguments` |

## 9. Slice status

1. Strict validation boundary — implemented, tests green.
2. Compiler + profiles — implemented, tests green.
3. Native adapter correctness — implemented (flat shapes, refusals, typed ids), tests green.
4. Constrained backend (Ollama `format`, OpenAI-compatible `response_format`) — implemented and fixture-covered. A live local-server run is **blocked in this environment**: no Ollama, llama.cpp, or vLLM installation and no usable local checkpoint (see section 11).
5. Governed prompt fallback — implemented (explicit per-Bot opt-in, versioned contract, strict whole-message parse, bounded repair), tests green.
6. Streaming parity — implemented via `hutch.toolcalling.streamassembly`, corpus + differential tests green.
7. Diagnostics UI — implemented as the inline "Tool calling" field (Route A, approved 2026-10-10); browser-verified at 1440/768/390/360 with screenshots, DOM metrics and a trace under `docs/realignment/artifacts/tool-compatibility/`.
8. Docs/packaging/verification — this document, models/safety docs, CHANGELOG, benchmark script, CLI parity.

## 10. Frontend diagnostic research (2026-10-10) and routes

Gate required by the project's design workflow: interface, audience, and constraints inspected
before proposing anything. Hutch's existing surface: SPA Bot settings, "AI service and model"
and "What it can do" panels (`src/hutch/server/static/app.js` around the `form-model` /
`tool-settings-title` sections), shared dark token system (`docs/design-system.md`,
`DESIGN.md`), `field`/`hint`/`panel` components, 44 px touch targets, non-color status cues.
Mobbin MCP is unavailable on the current (unpaid) plan - disclosed, not retried; Figma
Community could not be visually inspected in this environment, so real shipped product
screenshots were fetched from official documentation and read directly.

Inspected screens (downloaded and read, not remembered):

| # | Product / creator | Screen (source) | Pattern observed |
|---|---|---|---|
| 1 | Open WebUI (docs.openwebui.com, official docs) | Model editor - Capabilities | Capability truth as a grouped checkbox grid; "Advanced Params" and "JSON Preview" collapsed behind "Show" disclosures; single Save & Update |
| 2 | Open WebUI | Models list + view filter | Inline status labels next to each name (Private / Selected / Pinned) with a filter popover and per-row menus |
| 3 | Open WebUI | Chat controls - thinking/verbosity popover | Popover with labeled sliders and a footer note showing "Default - Balanced" so the inherited value is visible |
| 4 | LM Studio (lmstudio.ai docs) | Model list with gear action | "Edit model default config" lives behind a gear action per model row; technical columns (quant, size) stay scannable |
| 5 | Jan (jan.ai docs) | Model switcher gear | Model settings are reached from a gear adjacent to the model switcher, keeping model choice and model behavior adjacent |

Transferable patterns: put mode/capability truth where the model is chosen; make inherited or
automatic values visible ("effective: ..."); collapse advanced/diagnostic detail behind an
explicit disclosure; use labeled status text, not color alone. Do not transfer: Open WebUI's
many-tab admin structure (Hutch settings is one scroll page), its unrestricted custom parameter
editor (the assignment explicitly rejects an arbitrary untrusted grammar/template editor as the
default), or LM Studio's desktop-app chrome.

Presented routes (awaiting the owner's choice before implementation):

- **A (recommended): inline block in "AI service and model".** A "Tool calling" field under
  Model routing: select (Automatic / Provider-native / Constrained JSON / Prompt contract /
  No tools), an effective-mode line with evidence state, and a "Check compatibility"
  disclosure that loads `GET /api/v1/tool-compatibility` on demand with prerequisite rows and
  the last observation. Saved with the existing model form. Closest to screens 4-5; least
  chrome; keeps the fix one scroll from the symptom.
- **B: dedicated "Tool calling" panel** next to "What it can do" with its own save and a
  read-only evidence table. Mirrors screen 1's separation of capabilities; clearer for long
  explanations, adds another panel and more phone scrolling.
- **C: status-first compact row + Why popover.** Default state shows a status row
  ("Tools: provider-native - documented") with a "Why / change" disclosure containing the
  select and evidence, mirroring screens 2-3. Denser and calmer, but hides the primary control
  one level deep.

Approved: **Route A** (owner choice, 2026-10-10). Implemented in the SPA Bot settings and
browser-verified with artifacts listed in section 9.

## 11. Remaining gaps and uncertainties

- **Live local-model verification is blocked in this environment.** No Ollama,
  llama.cpp, or vLLM installation is present, and no usable local checkpoint is
  cached. Native/constrained behavior against a real server and an exact
  Mistral-family or Llama 8B checkpoint is therefore covered by fixtures and
  simulators only; the mode matrix labels those cells accordingly. Re-run
  `scripts/toolcalling_bench.py` and the conformance suites on a machine with a
  local stack before claiming live verification.
- **vLLM strict tool mode is documented, not enabled.** Hutch keeps best-effort
  native schemas and reports `strict` as available; enabling it would require
  schema rewrites (`additionalProperties: false`, all fields required) and is left
  as an explicit operator decision.
- **Large catalogs still generate one bounded envelope.** At 100 tools the
  constrained envelope is ~51 KB with ~12.4k contract tokens. Scoped tool
  selection and bounded two-stage generation are the designed follow-ups; they are
  not implemented, and `auto` never narrows a catalog on its own.
- **Multimodal tool results are unchanged.** Hutch's chat path does not expose
  images to models today, so the profile reports multimodal support as unknown and
  no image-tool-result conformance test exists.
- **The optional `jsonschema` engine is not installed here.** Execution uses the
  bounded validator (`hutch-bounded-v1`); every shipped catalog schema is
  certifiable on it, and schemas using unsupported keywords fail closed with a
  diagnostic rather than widening.
- **Approval/business-rule validation is unchanged, by design.** This feature
  adds no new authority; existing deny/ask/allow rules, sticky approvals, budgets,
  and receipts remain the enforcement point, and all generation modes converge on
  them.
