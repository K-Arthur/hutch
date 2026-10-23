# OpenRouter live route validation

Date: 2026-10-23. Isolated Hutch state: `/tmp/hutch-openrouter`. No key is stored in this repository.

## Account and key check

- `GET https://openrouter.ai/api/v1/key` returned `200`.
- The supplied key was identified as a **management/provisioning key** (`is_management_key: true`, `is_provisioning_key: true`). OpenRouter rejects management keys on completion endpoints. The first Hutch run correctly failed with an authentication error, but the connection check had reported success because it only read the public model catalog.
- Fixed: `OpenAICompatProvider.probe_models()` now detects management/provisioning keys and returns an actionable failure before the route is presented as usable. Regression coverage is in `tests/test_providers.py`.
- A temporary inference key was created with a **$1 limit** through OpenRouter's documented management API, used only for this test, and deleted afterward.

## Real calls

- `hutch connections test openrouter` with the inference key: authenticated; 449 models listed; `$1.00` key credit remaining.
- Text reply on `openrouter/openai/gpt-4o-mini`: `OK`; run `run_6d82082490a5` succeeded with 1 step.
- Tool round trip: `write_file` created `openrouter-tool-check.txt` containing `openrouter tool works.`; run `run_7ca939a7fd56` succeeded with 2 steps and recorded usage.
- Temporary key usage after both runs: `$0.00008775`; remaining limit `$0.99991225`.

## Scope

- This validates the OpenRouter account, authenticated discovery, a text reply and a native tool call through Hutch's built-in runtime.
- It does not validate every OpenRouter model or upstream provider, image input, a long stream, or a strict-currency ceiling. Those remain model- and account-dependent.
- The temporary inference key and local test state were removed after the checks.
