# OpenCode onboarding and real chat evidence

Date: 2026-10-22. Environment: Linux, Chromium 153 (Playwright), OpenCode CLI 2.1.2, isolated Hutch state directories under `/tmp`.

## What was run

- Empty-state first run at 1440, 900 and 390 px. The page reported the private OpenCode profile and its available models without a seeded bot or fabricated route.
- The first request was carried into setup. The quick path created an `opencode/opencode/big-pickle` assistant without starting a run.
- The advanced path showed the OpenCode runtime selector, ten model routes from the private profile, the provider dialog, tools, and the review step at desktop/tablet/phone widths.
- A real message was sent to the created assistant. OpenCode returned: “OK. I can help you plan your week and track follow-ups.”
- A real file-edit request produced an `OpenCode edit` approval. Hutch approved it once through the API; OpenCode wrote `hutch-opencode-check.txt` with exactly `hello from OpenCode` and the run succeeded. A later shell-only request produced an `OpenCode shell` approval, confirming the shell action did not fall through to an implicit allow.
- After the tool-list mapping fix, a bot created with only `files` and `web_fetch` produced an edit approval, wrote `mapped-tools-check.txt`, and completed with 2 steps and 5,168 recorded tokens. A bot with no shell tool cannot receive a shell permission from the generated OpenCode profile.
- The first visual pass caught provider-card overlap at desktop width. The dialog was changed to a single-column list; the evidence here is from the corrected build.
- Review also found and fixed: a released scheduler lease that became a permanent follower; OpenCode run step/token counters; newest-message pagination; a fresh setup server per OAuth request; shell policy bypass in Auto mode; and ignored bot tool lists.

## Screenshots

- `first-run-desktop.png`, `first-run-tablet.png`, `first-run-phone.png`
- `setup-step-0-desktop.png`, `setup-step-1-opencode-desktop.png`, `setup-step-1-opencode-tablet.png`, `setup-step-1-opencode-phone.png`
- `setup-step-2-tools-desktop.png`, `setup-step-3-review-desktop.png`
- `opencode-provider-dialog-desktop.png`, `opencode-provider-dialog-tablet.png`, `opencode-provider-dialog-phone.png` — provider catalog fixture, because the real profile already had usable free models and therefore skipped the dialog.
- `opencode-chat-live-desktop.png` — real free-model response.
- `opencode-tool-approval-desktop.png` — real edit approval.
- `opencode-tool-completed-desktop.png` — approved write plus final answer.

## Boundaries

- The provider dialog screenshot uses a deterministic catalog fixture to show the unconfigured state. It is not a claim that live OAuth completed.
- No paid provider key was available. OpenRouter/OpenAI/Anthropic live inference remains unverified; their adapters have fixture coverage and OpenRouter key verification now uses `/key`.
- OpenCode's approved tools run with the Linux user's authority, not inside Hutch's built-in bubblewrap shell sandbox.
- No physical phone, screen reader, or live OAuth provider flow was tested.
