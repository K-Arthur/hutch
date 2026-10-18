# Pre-fix full browser suite failure inventory — 2026-10-11

This snapshot was run on commit `b398e601` before the Studio focus and tablet layout changes. It completed with 177 passed, 29 failed and 8 teardown errors in 19m27s. The workflow policy-steps geometry failure was later fixed and its journey passed in the final full run.

## Failed cases

- `tests/e2e/test_browser.py::test_workflow_studio_policy_steps_start_answer_and_stop_at_all_viewports`
- `tests/e2e/test_browser.py::test_schedule_overview_shows_local_times_and_pauses_only_future_occurrences`
- `tests/e2e/test_browser.py::test_run_detail_reports_transcript_chain_verification_and_tampering`
- `tests/e2e/test_browser.py::test_opencode_coding_handoff_is_reviewed_and_responsive`
- `tests/e2e/test_browser.py::test_truncated_tool_source_card_opens_verified_plain_text_at_all_viewports`
- `tests/e2e/test_browser.py::test_verified_artifact_can_be_shared_with_another_chat_and_revoked`
- `tests/e2e/test_browser.py::test_mobile_navigation_traps_tab_and_restores_focus`
- `tests/e2e/test_browser.py::test_tool_permissions_are_clear_and_save_at_desktop_tablet_and_phone`
- `tests/e2e/test_browser.py::test_named_workspace_coordinator_is_first_class_direct_chat_at_responsive_sizes`
- `tests/e2e/test_browser.py::test_large_idle_roster_stays_compact_and_remains_searchable_and_keyboard_accessible`
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
