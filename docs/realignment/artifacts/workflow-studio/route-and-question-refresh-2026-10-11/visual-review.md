# Workflow route and question-card visual review

Reviewed on 2026-10-11 with Chromium 153.0.8010.12 and Playwright 1.63.0. The captures, traces, test results, and file hashes are stored beside this review.

The saved-workflow suggestion keeps its reason, simpler direct option, long method name, and explicit **Review & run** action together on desktop, tablet, phone, and compact phone. The 320px view wraps the long name without horizontal overflow. Enter opens the review dialog; Cancel starts nothing and returns focus to the refreshed suggestion after the transcript is replaced.

At 320px with WCAG text-spacing overrides, the card is 478px tall while the available chat scroll area is about 458px. The route-label/copy capture and the focused-action capture therefore record separate scroll positions. The action remains at least 44px tall and fully above the fixed composer when focused. Users can scroll to the card start to inspect its title and explanation. The forced-colors captures show the card using the system palette; the test also verifies that assistant and user transcript text resolve to `CanvasText`.

The specialist question is shown with its owner, prompt, reviewed constraint, both choices, and an answer action. At 1440px, 900px, and 390px it has no horizontal overflow; the 44px **Send answer** control stays above the composer. The test selects an answer by keyboard, forces a real transcript refresh while the card is open, verifies selection and focus preservation, then submits through the app API and a scripted loopback Ollama-compatible server. The durable question clears and the answer run succeeds. This is a deterministic integration fixture, not live model-quality evidence or a paired-phone authorization test.

The workflow-route journey made no model or external network requests and launched no workflow. The specialist journey made two requests to its scripted local endpoint; neither journey recorded browser page errors. The website’s separate four-size visual review remains in [marketing visual review](../../dynamic-workflows/marketing/visual-review.md).
