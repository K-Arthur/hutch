# Test and documentation impact audit - server-page topbar -> shared app-shell sidebar

Read-only audit. No source or test files were changed by this task; the only file written is this report.

- Repo/worktree: /home/kevina/CodingProjects/hutch, HEAD 548a2d6e, dirty shared tree. The chrome
  replacement was landing in the working tree WHILE this audit ran (another session). Every claim
  is pinned to the snapshot timestamps/hashes in section 0.
- Scope: tests depending on the old server-page chrome (header.topbar, nav.nav#primary-nav,
  #nav-toggle overlay, class="active", the Delete bot nav row, live-pill, stop-all); tests that
  read source files/static assets; template/lint/snapshot gates; doc claims; and a focused
  non-browser pytest baseline. Per instructions no e2e/Playwright test was run.

---

## 0. Snapshot and what changed in the tree

Implementation observed at 02:50-02:52 PT (files were still being edited during the audit):

- templates/base.html: topbar/nav markup replaced by .hutch-shell > .workspace#workspace (sidebar
  from new templates/macros/sidebar.html) + .hutch-workspace > header.app-top contextual header.
  Loads hutch-nav.css, hutch-shell.css, hutch-shell.js; no-js-nav.css noscript fallback retained;
  .skip skip link and footer.foot retained.
- src/hutch/server/nav.py (new): one nav model PRIMARY (chat/tasks/approvals), MORE
  (chats/overview/schedules/runs/runtime/skills/models/usage/bots), FOOT (connections/settings);
  normalize() aliases deletion -> bots.
- templates/macros/sidebar.html (new): <aside class="workspace" id="workspace">, <nav
  class="ws-nav" id="primary-nav"> (the id primary-nav is KEPT, now the sidebar nav; active marker
  is aria-current="page" only), details#monitor-nav More group, footer.ws-foot.
- static/hutch-nav.css (new, shared by SPA + server), static/hutch-shell.css (new, server only;
  breakpoint 900px; --app-top-h: 56px), static/hutch-shell.js (new drawer: inert on #workspace,
  scrim #ws-scrim, close #ws-close, focus trap, Escape -> #nav-toggle); hutch.css/hutch.js shrank
  (nav overlay removed); responsive.css/no-js-nav.css rewritten.
- pages.py: nav context from nav.py; /login and /pair now chrome=False; /bots/delete is no longer a
  navigation row (alias to Manage assistants; discovery moved to the assistant page danger zone).
- Unchanged and still present on full server pages: #nav-toggle, aria-expanded, the stop-all confirm
  form labelled "Stop all runs now. Kills child processes, not just the agent loop.", #live-pill
  titled "Live updates connected", footer.foot, a.skip[href=#main], main#main.container (now
  tabindex=-1).
- Tests already updated in the worktree by the implementation session:
  tests/test_models_page.py:40-41 (class="active" -> regex aria-current="page");
  tests/e2e/test_bot_deletion_ui.py:135-141,235-257 (renamed
  test_assistant_danger_zone_links_to_the_deletion_picker); tests/e2e/test_browser.py:7113-7226
  (rewritten test_server_page_navigation_uses_the_shared_sidebar); new
  tests/test_navbar_consistency.py (4 tests).
- Chrome file hashes at snapshot (02:50:16): base.html 9af2bc, nav.py 637b10, hutch-nav.css 1e8e02,
  hutch-shell.css bf4210, hutch-shell.js d9fc19, no-js-nav.css 23e022, pages.py ef0045 (trimmed to
  719 lines at 02:51:44); tests/e2e/test_browser.py 39ff7e (02:51:28),
  tests/test_navbar_consistency.py 72a94b.

Verdict: no pre-existing non-browser test still depends on the removed markup. The only assertions
that did depend on it were updated in the worktree during the audit. Remaining work is
(a) validation-script/doc updates, (b) a no-JS fallback gap, (c) browser re-runs for layout/
overflow-risk tests. Classifications below are by source inspection + TestClient render, not
Playwright.

---

## 1. Break / keep table - existing test assertions

Legend: KEEP = verified against the new markup, no edit; FIXED-IN-TREE = depended on old chrome,
already updated during the audit (verify in CI); UPDATE = still needs an edit; RISK = selector-free
assertion to re-run in a browser because layout/overflow changed.

1. tests/test_onboarding_page.py:61-63 (test_get_renders_chrome_less_empty_state) - asserts
   /onboarding has no id=primary-nav, no substring topbar, no class="foot". KEEP (chrome=False;
   verified in rendered HTML).
2. tests/test_onboarding_page.py:333-337 (test_existing_server_pages_keep_their_chrome) - asserts
   /legacy/connections contains id=primary-nav and class="foot". KEEP (both retained; verified).
3. tests/test_models_page.py:40 - nav entry present and active on /models. FIXED-IN-TREE 02:42:39
   (now regex <a href="/models"[^>]*aria-current="page").
4. tests/test_usage.py:206-207 (test_nav_has_a_usage_entry) - href="/usage" in /models HTML. KEEP
   (Usage row now inside details#monitor-nav, still in the DOM).
5. tests/test_dashboard.py:164-167 (test_stop_all_is_in_the_app_header_and_stops_a_run) - /stop-all
   in /legacy/connections, not in /login. KEEP (stop-all retained in .app-top-status; login is
   chrome=False).
6. tests/test_dashboard.py:66,71-72 - server page links hutch-pages.css, htmx.min.js, hutch.js.
   KEEP (all still linked).
7. tests/test_remote_pairing.py:52-72 - /pair must not expose the local state dir. KEEP for the
   final tree (login/pair are chrome=False; footer/state_dir absent). A mid-flight run failed here
   only because base.html landed seconds before pages.py - see section 3.
8. tests/test_fact_purge.py:288-304 - /bots/{name} has noscript, fact-purge markers and script; /
   shell references it. KEEP (baseline pass).
9. tests/e2e/test_browser.py:7113-7226 (was ...accessible_tablet_menu) - old assertions: horizontal
   #primary-nav with 8 exact hrefs / #nav-toggle overlay with aria-hidden+inert on nav, focus trap
   ending at the toggle, transition on #primary-nav. FIXED-IN-TREE 02:49-02:51 (shared-sidebar
   rewrite). Residual polish: replace the immediate assert rail.evaluate(el => el.inert) at 7148
   with wait_for_function (resize/media-query dispatch is async); the no-JS block only covers /usage
   where More is open - see gate G3.
10. tests/e2e/test_bot_deletion_ui.py:235-257 (was test_primary_nav_links_to_the_danger_zone_picker)
    - old: nav.nav a[href="/bots/delete"] count 1 and label "Delete bot". FIXED-IN-TREE 02:45:53
    (asserts the nav row is gone, opens details.danger-zone, follows "Open the deletion picker").
11. tests/e2e/test_bot_deletion_ui.py:135-141 evidence honest_limits - prose claimed the shared
    server-page NAV entry / #nav-toggle. FIXED-IN-TREE; committed
    docs/realignment/artifacts/completion-2026-10-29/deletion/capture.json is regenerated by the
    next e2e run (do not hand-edit).
12. tests/e2e/test_overlays.py:93-122 (test_server_page_confirm_form_and_tooltip) - on /models:
    stop-all accessible name, #live-pill titled tooltip, confirm dialog. KEEP (markup verified);
    re-run in browser for layout/stacking.
13. tests/e2e/test_browser.py:3202-3237 - /legacy/connections #main h1, body metrics, #live-pill
    exists/no animation. KEEP (live-pill and main#main retained); risk only.
14. tests/e2e/test_browser.py:7100-7110 (test_usage_budget_table_uses_labelled_phone_cards) -
    /usage at 390: scrollWidth === innerWidth. RISK; re-run (drawer is off-canvas at 390).
15. tests/e2e/test_wcag_measured_audit.py:209-225,304-314 - /models,/usage tables as named regions;
    72ch helper measure. KEEP/RISK; re-run (content now inside a 304px rail).
16. tests/e2e/test_wcag_measured_audit.py:519-532 (test_server_skip_link_adds_no_overflow_in_rtl) -
    /login first focus class="skip", RTL no overflow. KEEP (.skip retained; login chrome-less).
17. tests/e2e/test_experience_surfaces.py:60-88 - /models,/usage,/bots/*,/legacy/connections,/login,
    /pair at 1440/900/390/320: main h1 24px, body 16px, no overflow. KEEP/RISK; re-run.
18. tests/e2e/test_route_state_boundaries.py:178-202 (empty /usage,/models) and :261-295 (/models
    flash banner) - empty copy, no page errors, overflow at 1440/900/360. KEEP/RISK; re-run. Also
    RESIDUAL_GAPS at test_route_state_boundaries.py:51 cites base.html:34-38 - stale line refs;
    update refs/wording (evidence-only field).
19. tests/e2e/test_dropdown_controls.py:366-385 - /legacy/connections with JS off: select usable,
    16px, no overflow. KEEP/RISK; re-run; see the no-JS gap in section 4.
20. SPA-context tests that use the same ids (test_browser.py:7078-7097,7882...,11805,12647,12902;
    test_task_pages.py:108,167; test_radius_scale.py:104; test_design_system.py:1300,1606;
    test_overlays.py:149; test_route_state_boundaries.py:298-356) - SPA workspace/nav-toggle/fleet
    drawer behaviour. KEEP (SPA shell untouched; server duplicate ids live in another document).
21. tests/e2e/test_browser.py:7335-7352,7446+ (pair/login), test_live_updates_incremental.py:76
    (/bots redirects to SPA). KEEP (login/pair are now chrome=False; assertions are content-level).
22. tests/e2e/test_type_and_spacing_scale.py:106-130 - server routes intentionally skipped. KEEP.

Counts: 2 existing test areas already fixed in-tree (models active assertion; bot-deletion nav
discovery) plus the rewritten e2e server-nav test; 0 existing non-browser assertions still break;
0 known hard e2e failures after the in-tree rewrites, but items 12,14-19 need a browser re-run
before declaring green.

---

## 2. Tests that read source files / static assets

- tests/test_navbar_consistency.py (new, whole file): reads static/index.html, templates/base.html,
  served server pages, hutch.server.nav. NEW guard directly pinning this change (SPA sidebar rows
  vs nav.py label/href/order, both shells load hutch-nav.css, one sidebar + active destination,
  deletion->bots alias). 4 passed at 02:48:37. Keep it in every focused run; any rename of
  hutch-nav.css/hutch-shell.css or nav label/href/order breaks it by design.
- tests/test_studio_shell.py:51-87: reads served /static/style.css + studio.css + app.js, asserts
  .ws-nav button.attention. KEEP conditionally - the rule still lives at style.css:1803 /
  studio.css:400; hutch-nav.css now owns shared nav rows. If the SPA-only nav leftovers are removed
  from style.css/studio.css, add hutch-nav.css to _studio_css() (line 54) in the same change.
- tests/test_site_tokens.py:72-106 (token guard): scans ui.css, brand-tokens.css, style.css,
  studio.css, model-switcher.css + app.js, model-switcher.js, index.html. KEEP but coverage gap:
  new hutch-nav.css/hutch-shell.css and base.html/hutch.css are not scanned. Manual check at
  snapshot found 0 undefined fallback-less tokens, so no current failure. Recommended: add
  hutch-nav.css + hutch-shell.css to the definition/scan lists (and base.html to inline files).
- tests/test_studio_markdown.py:38-42: reads index.html (markdown.js present, before app.js). KEEP
  (SPA head edits added CSS links only; ordering unchanged).
- tests/test_outputs_integration.py:58-67: index.html widgets assets + app.js widget hook. KEEP.
- tests/test_widgets_static.py:108-139: index.html widget links and uplot<widgets<app order;
  app.js hook. KEEP (no script-order change; extra CSS links are inert to the assertions).
- tests/test_dashboard.py:50-95: server page shell includes hutch-pages.css, htmx.min.js, hutch.js;
  retired-route redirects; SPA home assets. KEEP (verified all still linked).
- tests/test_context_hygiene.py:192-194 + scripts/audit_context_hygiene.py: working-tree line
  counts vs .file-size-baseline.json (new source <=400 lines; frozen files shrink-only). The change
  temporarily broke this (pages.py frozen at 731 -> 736) but the implementation trimmed pages.py to
  719 at 02:51:44, so the navbar work is back within budget. Remaining 5 violations are pre-existing
  parked-tree work (bot_deletion.py 1067, cli.py +2, store.py +12, tests/test_bot_deletion.py 771,
  tests/test_commit_attribution.py 419). New files hutch-nav.css 184, hutch-shell.css 171,
  hutch-shell.js 79, nav.py 48 are under budget. Keep pages.py <= 731.
- tests/test_agent_map.py:140-141 + scripts/generate_agent_map.py --check: PRE-EXISTING failure at
  snapshot (map says 2172 in-scope files vs 2239 in the index; index has no staged changes). Once
  the new files are staged (nav.py, macros/sidebar.html, hutch-nav.css, hutch-shell.css,
  hutch-shell.js, tests/test_navbar_consistency.py) the map changes again: run npm run agent:map and
  stage the generated map in the same commit.
- tests/test_emoji_audit.py:28-40: repo-wide emoji/icon ban. KEEP - scripts/audit_emoji.py clean at
  snapshot (12,555 files scanned); new files must stay emoji/icon free.

---

## 3. Baseline pytest results (non-browser, focused)

Documented quiet invocation shape (UV_CACHE_DIR is needed because ~/.cache is read-only in this
sandbox):

    export UV_CACHE_DIR=/tmp/uv-cache-baseline
    uv run --frozen --no-sync pytest -q --no-header --tb=line \
      tests/test_onboarding_page.py tests/test_models_page.py tests/test_site_tokens.py \
      tests/test_studio_markdown.py tests/test_outputs_integration.py tests/test_widgets_static.py \
      tests/test_dashboard.py tests/test_usage.py tests/test_fact_purge.py tests/test_remote_pairing.py \
      tests/test_studio_shell.py tests/test_desktop_sidecar.py

Run A - 02:37:55-02:40:34, mid-flight tree (base.html rewritten 02:39:40; pages.py chrome=False for
login/pair landed 02:39:49): 1 failed, 191 passed, 6 skipped. Failure:
tests/test_remote_pairing.py::...passkey_session_is_revocable line 70 - /pair briefly rendered the
new footer (state dir) in the ~9s window before chrome=False landed. Transient, not a regression.

Run B - 02:43:28-02:45:52, coherent implementation: 192 passed, 6 skipped, 0 failed (141.70s).
During the run hutch-nav.css, no-js-nav.css, test_models_page.py and test_bot_deletion_ui.py were
edited; none of those edits affects the 12 files' outcomes (models test already updated before it
ran; CSS is not asserted by this group).

Run C - 02:50:16-02:52:26, final focused post-rewrites: 137 passed, 0 failed, 0 skipped (130.18s):
tests/test_navbar_consistency.py tests/test_models_page.py tests/test_onboarding_page.py
tests/test_dashboard.py tests/test_usage.py tests/test_fact_purge.py tests/test_remote_pairing.py
tests/test_studio_shell.py (pages.py trimmed mid-run).

Run D - repo gates 02:48:52: tests/test_context_hygiene.py tests/test_emoji_audit.py
tests/test_agent_map.py -> 2 failed, 30 passed. Failures: test_real_repository_has_no_context_violations
(6 violations then; pages.py growth since fixed -> 5 pre-existing remain) and
test_real_repository_check_passes (stale agent map, pre-existing). Emoji clean.

New-guard standalone at 02:48:37: tests/test_navbar_consistency.py -> 4 passed. It initially had 2
failures (badge text captured as "Needs you0" in the SPA parser; class="active" falsely matched the
/usage period selector) which the implementation fixed at 02:48:12 by scoping both correctly.
No full-suite run and no e2e/Playwright run.

---

## 4. Template / lint / snapshot gates

- No HTML/Jinja template lint or HTML snapshot/diff gate exists (package.json has CSS builds +
  audits only; no prettier/eslint/htmllint/jinja lint). The de-facto template contracts are the new
  tests/test_navbar_consistency.py and the rewritten e2e shared-sidebar test.
- npm run check:agent IS relevant. It runs context hygiene + tool contracts + constitution + agent
  map. Current status: tool contracts pass (40 tools), constitution passes, context hygiene exits 1
  only for 5 pre-existing parked-tree violations (navbar-caused pages.py growth is already fixed;
  pages.py now 719 <= frozen 731), agent map fails for pre-existing drift (regenerate after staging
  the new files).
- scripts/validate_responsive.py (Playwright evidence harness) MUST be updated - it hard-codes the
  old model:
  scripts/responsive/checks.py:169-193 (NAV_JS) measures #primary-nav visibility/overflow and toggle
  display; needs the rail (#workspace) + drawer model and the 900px (not 1024px) boundary.
  scripts/responsive/capture.py:151-165 says horizontal nav visible above 1024px, toggle hidden
  above 1024px, no-JS all links visible - update to the rail + details model at 900px.
  scripts/responsive/states.py:132-160 (style_scope) reads --topbar-h and .run-head sticky offset;
  the server shell now uses --app-top-h (56px, hutch-shell.css:14; responsive.css:150-153 keeps
  --topbar-h only as the SPA legacy fallback). This check will fail as written.
  scripts/responsive/states.py:204-219 (server_nav_overlay) opens #nav-toggle at 375 AND 1024; 1024 is
  no longer a drawer width (>900), so use e.g. 768/900 and wait for #workspace.open.
  scripts/responsive/config.py:74-83 server surfaces are fine; pages-login/pair are now chrome-less
  (nav check skips them).
- scripts/validate_overlays.py (Playwright evidence harness) code still matches: scenario_server_confirm
  (184-200) uses the retained stop-all confirm on /models; scenario_tooltip (221-231) uses the
  retained #live-pill. Its committed evidence and the docs/overlays A6 nav-sheet row are stale -> rerun
  with a new label.
- CI (.github/workflows/ci.yml:40-41) runs the full pytest including tests/e2e, so the rewritten e2e
  tests are part of the landing gate; responsive/overlay harnesses are manual evidence runs.
- No-JS contract finding (not covered by the rewritten e2e test): with JS disabled the rail is a
  static list (no-js-nav.css), but details#monitor-nav is only rendered open when the active
  destination is in MORE (pages.py nav_more_open). On routes whose active item is primary/footer
  (e.g. /legacy/connections, 404/error pages) the 9 More destinations are hidden without JS. The
  rewritten e2e no-JS block checks /usage (active=usage -> More open) so it passes; the responsive
  no-JS surfaces are /models,/usage,/bots/... (all More-active) or chrome-less login/pair, so the
  harness may pass too. Fix no-js-nav.css (force #monitor-nav contents visible) and add a no-JS check
  for /legacy/connections plus an error page.

---

## 5. Documentation claims that depend on the old chrome

Current-behaviour docs now stale (update/annotate; historical review evidence should be superseded
by a new run/label, not rewritten):

- docs/responsive/tasks/02-server-navigation-model.md:62-73 (Outcome: overlay <=1024, 9-link single
  row at 1180/1366, no-JS 9/9 links) - superseded by the shared sidebar; add a follow-up
  task/outcome or annotate.
- docs/responsive/STATE.md:18,51 and docs/responsive/COMPLETION.md:21,36 - status rows for task 02.
- docs/responsive/inventory.md:84-86,112,193,226 - "hutch.css: server-page shell: topbar, nav
  breakpoints", "hutch.js (180-269) server nav overlay controller", "base.html ... topbar and nav".
- docs/responsive/research-2026-10-29.md:54-55 ("Server pages: no app shell");
  docs/responsive/audit.md:23,65,67,70,71,153,155; tasks/04:8,20,31,66; tasks/05:18;
  tasks/06:25-26. Historical audit docs pinned to earlier commits - leave findings, add a
  superseded-by note or regenerate via a new responsive run.
- docs/overlays/audit.md:21 (A6 server nav sheet contract), docs/overlays/inventory.md:82,
  docs/overlays/COMPLETION.md:111 - rerun scripts/validate_overlays.py and update the A6 row to the
  sidebar drawer (left 300px/86vw, first focus = brand, scrim + inert).
- docs/requirements.md:25 (UI-2 "Stop all in every header") - KEEP: .app-top-status keeps stop-all
  in the header on every chrome page.
- docs/design-system.md:271 ("one workspace sidebar, contextual header") - KEEP; now true for server
  pages too.
- docs/brand-assets.md:53 ("Studio sidebar and server header: 22px Small mark ...") - wording:
  server header -> server shell rail (same lockup).
- docs/onboarding/slices/slice-01.md:42 (onboarding chrome-less claim) - KEEP (verified).
- docs/realignment/ledger.md:1459,4640,4658 (historical "topbar Stop all form" entries) - do not
  rewrite; append-only history.
- docs/realignment/artifacts/completion-2026-10-29/deletion/capture.json + screenshots - regenerated
  by the next e2e run (current text still mentions the shared server-page NAV entry).
- tests/e2e/test_route_state_boundaries.py:51 RESIDUAL_GAPS cites base.html:34-38 - update line
  refs/wording.

---

## 6. Recommended minimal test edits (do not apply blindly - several are already done)

Already applied in the worktree during the audit: tests/test_models_page.py:40-41;
tests/e2e/test_bot_deletion_ui.py (discovery test + evidence limits);
tests/e2e/test_browser.py test_server_page_navigation_uses_the_shared_sidebar; new
tests/test_navbar_consistency.py.

Still recommended:
1. tests/e2e/test_browser.py (new sidebar test): replace the immediate
   rail.evaluate("el => el.inert") after set_viewport_size (line 7148) with wait_for_function on
   document.getElementById('workspace').inert (resize/media-query dispatch is async). Add a no-JS
   assertion for a route whose active item is not in More (e.g. /legacy/connections): all 14
   destinations visible without JS.
2. src/hutch/server/static/no-js-nav.css: force #monitor-nav links visible (or details[open]) so
   every destination stays reachable without JS on every route (section 4).
3. scripts/responsive/checks.py:169-193, capture.py:151-165, states.py:132-160,204-219: rewrite the
   nav model to rail/drawer at 900px, --app-top-h, and all-destination no-JS measurement.
4. tests/test_site_tokens.py:88,99: add hutch-nav.css and hutch-shell.css to the token-guard
   definition/scan list (and base.html to inline files) - coverage only.
5. tests/test_studio_shell.py:54: include hutch-nav.css in _studio_css() if the SPA nav rules move
   out of style.css/studio.css (keep the .ws-nav button.attention contract).
6. Landing hygiene: npm run agent:map after staging nav.py, templates/macros/sidebar.html,
   hutch-nav.css, hutch-shell.css, hutch-shell.js, tests/test_navbar_consistency.py; keep pages.py
   <= 731 lines for context hygiene.
7. Browser re-runs before declaring green: test_overlays.py::test_server_page_confirm_form_and_tooltip;
   test_browser.py::test_usage_budget_table_uses_labelled_phone_cards;
   test_wcag_measured_audit.py::test_server_page_tables_are_named_keyboard_regions and
   ::test_helper_text_keeps_the_72ch_measure;
   test_experience_surfaces.py::test_active_server_rendered_pages_share_type_and_readable_layout;
   test_route_state_boundaries.py::test_first_run_empty_state_and_cta and
   ::test_models_server_flash_error_banner;
   test_dropdown_controls.py::test_server_select_form_remains_usable_without_javascript.
8. Docs list in section 5; rerun scripts/validate_overlays.py --label <new> for evidence.

---

## 7. Method and limits

- Grepped all tests/** for #primary-nav, primary-nav, nav-toggle, topbar, .nav a, navbar, skip,
  aria-current, .ws-nav, #workspace, live-pill, stop-all, #topbar-new-bot, nav-visible, no-js, plus
  source-reading patterns (read_text/read_bytes/__file__/static//templates/), then read every hit in
  context.
- Current chrome confirmed by rendering pages with TestClient(create_app()) and reading the new
  templates/CSS/JS; baseline runs are the exact commands/results above.
- Not run per instructions: full suite, tests/e2e/, Playwright, responsive/overlay harnesses; those
  statuses are source-inspection results requiring a browser run for final confirmation.
- The tree was edited concurrently by the implementation session; snapshot hashes and run timestamps
  are recorded in sections 0 and 3 so results are reproducible.

