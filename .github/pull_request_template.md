## Behavior change

<!-- What changed, and why? Describe the user-visible behavior rather than the file list. Write "None" for a docs-only change. -->

## Linked issue or ADR

<!-- Link the issue, ADR (docs/adr/), or discussion this implements. Write "None" only for maintenance-only changes. -->

## Checks run

<!-- List the exact commands and their results. Do not write only "tests pass"; show the command and its summary line. -->
<!-- Examples:
`npm run check:agent` - passed
`uv run --frozen --no-sync pytest -q --no-header --tb=line tests/test_x.py` - 12 passed
`npm run build:css` - site and app CSS rebuilt from sources
`cargo check --manifest-path desktop/Cargo.toml` - finished
-->
<!-- Note any check you did not run and why, for example browser tests that need a Chromium revision. -->

- [ ] `npm run check:agent`
- [ ] Focused tests for the touched behavior
- [ ] Fast suite (`uv run pytest --ignore=tests/e2e`) when the change warrants it
- [ ] Site or app CSS rebuilt from sources when `app/src/` or the website CSS sources changed
- [ ] Repository hygiene check on staged blobs (`python3 scripts/check_repo_hygiene.py`) and the Gitleaks command from CONTRIBUTING.md
- [ ] `cargo check` or `cargo test` for any desktop crate touched

## Visible UI changes

<!-- Delete this section if the change is not visible. Attach screenshots or a short recording and state the OS, desktop session, theme, viewport, and the dashboard route or browser used. -->
<!-- If a capture is retained as evidence, place it under `docs/realignment/artifacts/<name>/` and link it here. -->

## Documentation, claims, and evidence

<!-- Docs are claims that need evidence: current behavior, a test, or a dated measurement. Keep experimental status and verification limits explicit. -->
<!-- For wording on the marketing site, in docs, or in the UI, cite the approved claim and its evidence path, for example `docs/marketing-site.md` or `docs/realignment/ledger.md`. Do not add security superlatives, benchmarks, testimonials, "free forever", absolute privacy claims, or "production-ready" language. The stage term is "development preview". -->

- [ ] User-visible behavior is documented, or the change needs no documentation
- [ ] New or changed claims point at a test, a dated measurement, or an evidence path
- [ ] Experimental and unavailable behavior stays labelled

## Boundaries and safety

- [ ] The change preserves the local-first, explicit-approval model and does not broaden tools, permissions, provider access, or data sharing as an incidental side effect
- [ ] Deliberate boundary changes are described above and covered by tests
- [ ] No secrets, tokens, .env files, state directories, or transcripts are included

## Commit and hygiene

- [ ] Commit messages carry no AI-tool attribution, generated-by signature, or AI session link, per `docs/commit-attribution-policy.md`
- [ ] Only the files reviewed for this change are staged; unrelated in-flight work in the checkout is untouched
- [ ] The change stays focused and does not reformat unrelated code
