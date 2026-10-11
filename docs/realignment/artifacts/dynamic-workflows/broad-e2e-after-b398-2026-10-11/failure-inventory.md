# Final full browser suite failure inventory — 2026-10-11

The final browser suite was run after the Studio focus and responsive-layout fixes on the updated worktree at base commit `b398e601`. The Studio policy journey, route card and specialist-question journeys passed; the suite ended with **181 passed, 25 failed and 8 teardown errors in 19m42s**. This is not green. The remaining failures and teardown errors have not been individually reproduced or classified.

## Failed cases

- `tests/e2e/test_browser.py::test_opencode_coding_handoff_is_reviewed_and_responsive`
- `tests/e2e/test_browser.py::test_truncated_tool_source_card_opens_verified_plain_text_at_all_viewports`
- `tests/e2e/test_browser.py::test_verified_artifact_can_be_shared_with_another_chat_and_revoked`
- `tests/e2e/test_browser.py::test_mobile_navigation_traps_tab_and_restores_focus`
- `tests/e2e/test_browser.py::test_tool_permissions_are_clear_and_save_at_desktop_tablet_and_phone`
- `tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes`
- `tests/e2e/test_browser.py::test_duplicate_bot_starts_from_safe_editable_setup_without_copying_authority`
- `tests/e2e/test_browser.py::test_small_workspace_has_one_roster_and_legacy_routes_do_not_trap_back`
- `tests/e2e/test_browser.py::test_bot_workspace_modes_are_clear_and_persist_across_settings[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_bot_workspace_modes_are_clear_and_persist_across_settings[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_bot_workspace_modes_are_clear_and_persist_across_settings[390-844-phone]`
- `tests/e2e/test_browser.py::test_bot_workspace_modes_are_clear_and_persist_across_settings[320-740-compact-phone]`
- `tests/e2e/test_browser.py::test_local_browser_handoff_setting_is_explicit_and_persists[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_local_browser_handoff_setting_is_explicit_and_persists[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_local_browser_handoff_setting_is_explicit_and_persists[390-844-phone]`
- `tests/e2e/test_browser.py::test_bot_and_conversation_switches_isolate_unsent_drafts`
- `tests/e2e/test_browser.py::test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus[390-844-phone]`
- `tests/e2e/test_browser.py::test_composer_options_rehearsal_and_cancelled_notice[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_composer_options_rehearsal_and_cancelled_notice[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_composer_options_rehearsal_and_cancelled_notice[390-844-phone]`
- `tests/e2e/test_browser.py::test_scoped_fact_review_revision_conflict_and_memory_off[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_scoped_fact_review_revision_conflict_and_memory_off[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_scoped_fact_review_revision_conflict_and_memory_off[390-844-phone]`

## Teardown errors

- `tests/e2e/test_browser.py::test_mobile_navigation_traps_tab_and_restores_focus`
- `tests/e2e/test_browser.py::test_bot_and_conversation_switches_isolate_unsent_drafts`
- `tests/e2e/test_browser.py::test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_resource_replay_updates_chat_after_gap_without_losing_draft_or_focus[390-844-phone]`
- `tests/e2e/test_browser.py::test_composer_options_rehearsal_and_cancelled_notice[1440-1000-desktop]`
- `tests/e2e/test_browser.py::test_composer_options_rehearsal_and_cancelled_notice[900-1024-tablet]`
- `tests/e2e/test_browser.py::test_composer_options_rehearsal_and_cancelled_notice[390-844-phone]`
