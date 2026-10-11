# Persona verification checkpoint

These files record the local pre-integration checkpoint on `persona/adaptive`, before importing the latest local
`main` commit `63b2712`.

- `offline-suite.log` is the full offline run: **2,048 passed**.
- `browser-suite-pre-main.log` is the complete `tests/e2e` run. It records **29 failed, 181 passed, 8 teardown
  errors**. The failure list includes a stale inspector-role assertion that was corrected afterward; do not treat this
  historical full-suite result as the final integrated run.
- `persona-focused-browser.log` is the focused live-preview and answer-rewrite run after updating that assertion:
  **2 passed**.

The task plan records how the pre-integration failures compare with the earlier clean-base run and which isolated checks
passed on `63b2712`. No assertions were removed or weakened.

After merge commit `15e1649`, the complete offline suite passed (**2,116 passed**); see `offline-suite-integrated.log`.
The dedicated migration suite was rerun after the final test additions and passed (**32 passed**); see
`migration-suite-integrated.log`.
The complete integrated browser run is recorded in `browser-suite-integrated-stalled.log`: it remained inside the
known responsive workspace-settings case at 33% for over seven minutes, then was interrupted at 20 minutes. The focused
integrated browser retry in `browser-focused-integrated-enospc.log` ran while `/tmp` was full and failed creating
Chromium/trace state (`ENOSPC`); those failures are environment-contaminated. The focused rerun with temporary files
moved to `/var/tmp`, recorded in `browser-focused-integrated.log`, passed **6 tests**: live preview, answer rewrite,
specialist clarification, workflow-pill dimensions, and the Runtime page. These task-specific Chromium runs did not use a
provider. `persona-live-preview-2026-10-11/validation.json` records zero horizontal overflow from 320 to 1440 CSS pixels,
including the 720×480 effective-width check.
