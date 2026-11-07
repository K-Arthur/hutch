# Phase 8 design: website and documentation

Goal: every public sentence about local models and offline work maps to a dated row in
`02-PROGRESS.md`; the local/offline boundary is stated in the site's own words; the
compatibility and setup docs carry the per-runtime evidence and limits.

## Tasks

### T8.1 Local and offline boundary on the site
Files: `website/index.html`, `website/llms.txt`, `website/src/input.css` only if styling
is needed.
- Add a short visible "Local and offline" block in `#runs` with a three-row boundary
  table: worker egress enforced, model server not isolated, runtime updates/telemetry not
  controlled by Hutch. State the allowed sentence ("this run's worker could not reach the
  network, and its model route went only to your loopback address") and the disallowed
  one ("nothing leaves this machine").
- Name the verified local runtimes and versions (Ollama 0.40.13/0.40.15, llama.cpp
  b12144, LM Studio llmster 0.0.27-1, 2026-11-06) and the limits (one host; no GPU,
  vLLM, SGLang, macOS or Windows evidence).
- Update the JSON-LD `featureList` and `dateModified`; extend the FAQ answer "What
  actually leaves my machine?" with the boundary and the EC-28 confirmation. Keep the
  FAQ JSON-LD and visible markup in parity.
- `llms.txt`: add the boundary sentence and the local runtime list.

### T8.2 Marketing claims ledger
File: `docs/marketing-site.md`.
- Add a "Local models and offline" subsection under the capability language table with
  the exact states, dated evidence and limits; update the capability table's
  Experimental row to name local runtime introspection, the EC-28 confirmation and the
  measured state labels.
- Update the screenshot/evidence notes only if a capture changes.

### T8.3 Compatibility rows
File: `src/hutch/data/compat.json`.
- Update `ollama-native` with the 2026-11-06 live evidence (0.40.13/0.40.15, tools,
  vision, streaming, cloud signal, num_ctx, offline) and its limits.
- Add `llamacpp-server` and `lmstudio-native` rows as `experimental`, naming the build,
  the native endpoints, the applied-window source, tools/vision, and what was not run.
- Add a `vllm-sglang-openai` row as `experimental` with "not installed; OpenAI-compatible
  seam only" so the absence is explicit.
- Set `reviewed_on` to 2026-11-06.

### T8.4 Product docs
Files: `docs/models.md`, `docs/runtime-setup.md`,
`docs/realignment/offline-models-2026-10-31.md`.
- `docs/models.md`: add a "Local runtimes on this machine" section with the measured
  state labels (ready/loading/needs_key/down/unknown), the applied-window sources, the
  EC-28 confirmation, and the verified/unverified rows from `02-PROGRESS.md`.
- `docs/runtime-setup.md`: confirm the per-runtime recipes and add the llama.cpp/LM Studio
  setup facts (stock port 9931, `--jinja`, `--mmproj`, `--api-key`, LM Studio projector
  naming), the offline recipe, and the model-server boundary.
- `docs/realignment/offline-models-2026-10-31.md`: append a section 10 for Phase 7/8
  (frontend state labels, EC-28, the public claim) and link the evidence.

### T8.5 Release checklist
File: `docs/release-checklist.md`.
- Update baseline counts only if the suite counts changed; record the exact commands.

## Validation
- `tests/test_site_tokens.py`, `tests/e2e/test_website.py`, `tests/test_compat.py`,
  `tests/test_models_page.py`, `tests/test_route_sharing.py`.
- `npm run build:css --silent` if `website/src/input.css` changes; then
  `capture_marketing_top.py` at 360/768/1280/1920, light and dark, view the images, fix
  defects, record zero overflow and zero console errors.
- `npm run check:agent`, `npm run audit:context`, `scripts/audit_emoji.py`.

## Constraints
- No claim without a dated ledger row. No "nothing leaves your machine". Do not describe
  the model server as isolated. Do not add a vendor partnership or a support claim.
- Edit `website/src/input.css` only if a new class is needed; never generated CSS.
