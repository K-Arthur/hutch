# First-run request and AI readiness research (2026-10-23)

## Scope and approved direction

The audited surface is the empty Chat workspace for a first-time user who wants to
get Hutch ready and complete a first useful task. The approved route is **request
plus readiness panel**: keep the request primary, show the AI service Hutch found
beside it on wide layouts, and stack the panel in reading order on narrow layouts.
The decision was approved before implementation. The existing graphite palette,
emerald action, azure focus, Archivo headings, system-sans prose, rounded scale,
and semantic status colours remain fixed.

## Evidence inspected

| Reference | Inspected | Useful pattern | Limit |
|---|---|---|---|
| [Lumo guest chat](https://lumo.proton.me/guest) | Live public interface at 1280×800 and 375×812; rendered text, controls, bounds, and model menu | A short working area keeps the request and AI choice together; model names carry short task-oriented descriptions | DOM and computed layout only; remote images could not be fetched by the available image fetcher |
| [HuggingChat welcome](https://huggingface.co/chat/) | Live public interface at 1280×800 and 375×812; rendered dialog and empty-chat controls | One explanation and one clear forward action before the chat surface | A promotional welcome overlay should not be copied; no inference was run |
| [NN/g: New Users Need Support with Generative-AI Tools](https://www.nngroup.com/articles/new-AI-users-onboarding/) | Article text and study examples | Keep onboarding brief, use broad examples, and place help at the decision point | Small qualitative study; not evidence about Hutch users |
| [Jan issue 6854](https://github.com/janhq/jan/issues/6854) | Issue body | Named failures: configuration overload, advanced controls exposed too early, steep setup | Product issue report, not measured prevalence |
| [Jan issue 7658](https://github.com/janhq/jan/issues/7658) | Issue body and resolution | A model selected in onboarding must survive into chat; “select a model” is a poor first screen | Regression report from one product |
| [W3C status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages) | Normative guidance | Announce readiness changes without taking focus | Conformance guidance, not visual direction |
| [web.dev CLS guidance](https://web.dev/articles/optimize-cls) | Guidance | Reserve stable space for late content | General web guidance |

Figma Community discovery returned HTTP 403 in this session, and the available
remote-image fetch route rejected JPEG/PNG content. No unopened Community frame
is described here. Lumo and HuggingChat were read through their rendered DOM,
computed styles, and bounding boxes rather than visual screenshots, so their
observations are structural rather than a claim about fine visual detail.

## Confirmed defects in the incumbent first-run surface

- The request input was not stored; returning from **Use another provider**
  lost the entered request.
- The first-run status checked OpenCode alone but used the global wording
  “No AI model is available yet,” even when another provider route existed.
- The status called a workspace/default proposal “your saved AI choice” without
  distinguishing saved from verified.
- At 375×812 the primary action ended below the viewport and the readiness
  status appeared farther down.
- The first-run styles used off-scale spacing, radii, and one-off shadows.

## Implementation decisions

- Store the request in tab-scoped `sessionStorage`, with an in-memory fallback.
  Preserve it through provider navigation, reload, setup Cancel, and connection
  setup; clear it after successful creation or **Clear request**.
- Resolve saved workspace choice, OpenCode status, and built-in model routes
  independently. Distinguish **Ready**, **Saved**, **Choose AI**, and **Check
  failed**. A failed partial check is not reported as “no service exists.”
- Pass the resolved AI choice into setup. If no usable service is known, the
  first-run primary action leads to AI service selection; the technical model
  form is not the first destination.
- Use one polite status region; do not take focus when the async result arrives.
  The deterministic test holds the readiness response, focuses the request,
  then releases it and verifies focus did not move. Reserve the panel's text
  area to reduce movement.
- Pair request and readiness above 1100px; stack below. Keep the setup action
  inside the initial 375×812 viewport and the readiness heading visible. The
  workbench measures 1040px at 1440 and 944px at 1280.
- Use existing spacing, radius, shadow, surface, text, and interaction tokens.

## Validation recorded

- `tests/e2e/test_design_system.py::test_first_run_draft_and_ai_readiness_survive_connections_and_failures`
  covers the empty-request primary CTA, provider detour, reload, setup Cancel,
  missing-service routing, all-checks-failure retry, clear, and phone/desktop
  screenshots. It uses deterministic API responses and makes no provider call.
- `tests/e2e/test_design_system.py::test_first_run_readiness_distinguishes_saved_route_and_partial_states`
  covers a saved workspace default, a discovered ready route that reaches
  setup with its first-run provenance, and a single failed readiness check
  that reports **Choose AI** with Retry instead of claiming no service exists.
- `tests/e2e/test_design_system.py::test_assistant_first_run_and_app_catalog_use_familiar_visual_language`
  was updated to keep the setup handoff deterministic with a ready OpenCode
  status fixture.
- `docs/realignment/capture_first_run.py` recaptured the actual empty app at
  1440×1000, 900×1024, 390×844, and 320×740 with no bots, conversations, runs,
  approvals, or configured connections. No provider call was made.
- The marketing proof and copy were refreshed from that capture. See
  `docs/realignment/visual-validation.md` for the opened images, responsive
  measurements, keyboard checks, and remaining limits.
