# Adaptive-persona rollback browser evidence

The test starts the actual Hutch app with saved assistant and conversation settings, enables the local rollback flag,
and checks that saved values remain readable while style controls become read-only. It verifies that an unsent local
next-reply draft survives but is not displayed as active, and that answer-rewrite and feedback controls are hidden.
No provider or external request is made.

The six related browser journeys passed together (**6 passed in 22.75 s**) with:

```sh
TMPDIR=/var/tmp .venv/bin/python -m pytest -q \
  tests/e2e/test_design_system.py::test_adaptive_persona_controls_round_trip_recover_conflicts_and_stay_local \
  tests/e2e/test_design_system.py::test_static_persona_examples_are_labeled_local_and_responsive \
  tests/e2e/test_design_system.py::test_persona_live_preview_is_explicit_isolated_cancellable_and_responsive \
  tests/e2e/test_design_system.py::test_adaptive_persona_rollback_is_visible_read_only_and_preserves_local_draft \
  tests/e2e/test_design_system.py::test_answer_rewrite_controls_preserve_chat_state_and_hide_for_external_runtimes \
  tests/e2e/test_design_system.py::test_answer_feedback_stays_local_revisioned_and_accessible
```

The rollback journey saved screenshots at 320, 360, 720×480, 768 and 1440 CSS pixels. Each had zero horizontal
overflow. `validation.json` records browser version, UI states, console and page errors, failed same-origin
responses, external requests, inference requests, reduced-motion state, and source hashes. `trace.zip` preserves
the browser trace. The screenshots were inspected manually.
