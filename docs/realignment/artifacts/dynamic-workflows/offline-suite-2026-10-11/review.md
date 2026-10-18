# Offline suite classification

The complete non-browser suite ran at `f1562329` in a disposable detached checkout and finished with 2,186 passed and 2 failed in 640.23 seconds. It is not green.

`test_connection_models_known_from_bots_appear_with_their_state` failed on the run tree and reproduced on main baseline `6221cc25` with `PYTHONPATH` explicitly pointing at the baseline checkout. The test sets `OPENCODE_API_KEY=k`; a real catalog call returns the generic unavailable note even though the connection route is marked ready. The exact upstream/provider error is not retained. This is a pre-existing catalog/test-fixture failure unrelated to dynamic workflows.

`test_loopback_broker_refuses_a_request_after_close_starts` failed because the shared `TMPDIR=/<local-path-redacted> generated a Unix socket path beyond the platform limit. The test also fails on baseline `6221cc25` with that long path and passes with `TMPDIR=/<local-path-redacted> classify it as a pre-existing test-environment path-length failure.

The separate broad browser suite remains non-green (181 passed, 25 failed, 8 teardown errors); see `broad-e2e-after-b398-2026-10-11/`. Targeted workflow and website browser journeys are verified separately. Exact commands, outputs, tree hashes, and per-file hashes are recorded in `results.json`.
