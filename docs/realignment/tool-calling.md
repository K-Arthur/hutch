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

## 7. Measured budgets (to be filled during slice 8)

Baseline to capture before optimization: compilation cold/warm ms at 1/10/100 tools; prompt
overhead tokens for native vs constrained contract; first-validated-call latency; repair rate.
No optimization may loosen validation to meet a budget.
