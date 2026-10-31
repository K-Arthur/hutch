# 06 - Validation ledger

Exact commands and observed results. Status: in progress. Hosted live verification is `BLOCKED` for
this delivery because no provider credentials exist in the execution environment; nothing below should
be read as proof that a hosted provider works live.

## Environment probes

| Probe | Command | Observed | Verdict |
|---|---|---|---|
| Provider credential variables | names-only scan of the process environment | 0 provider-like variables | BLOCKED for hosted live calls |
| Local inference services | HTTP probe of 127.0.0.1:11434, 1234, 8000, 30000, 8080 | all unreachable (000) | no local model to exercise |
| Installed coding CLIs | `command -v` / `--version` | claude 2.1.314; codex and opencode installed (opencode version probe blocked by read-only log path); gemini/qwen/pi absent | CLI runtimes not live-exercised |
| Artifact | `artifacts/env-probe.txt` | recorded | evidence |

## Baseline automated tests (HEAD 1c454c32, clean worktree)

| Suite selection | Command | Result |
|---|---|---|
| providers, connections, authority, model switcher, models layer, opencode API/login, chat vision, media jobs/providers | `.venv/bin/python -m pytest -q` with `PYTHONPATH=<worktree>/src` | pending at time of writing; recorded on completion |

An earlier run on the shared main checkout (which included another session's in-progress edits) passed
230 tests with 1 skipped in 165 s; it is not a clean baseline and is recorded only as context.

## Live provider validation

| Provider | Auth | Catalogue | Inference | Streaming | Tools | Capability | Verdict |
|---|---|---|---|---|---|---|---|
| all hosted providers | not available | not available | not available | not available | not available | not available | BLOCKED |

## Visual validation

| Surface | Viewports | Status |
|---|---|---|
| /providers, /legacy/connections, /models | 1440x960, 1280x720, 900x1024, 390x844, 320x740 | pending |
| website index | same five | pending |

## Gaps to close before completion

- Record the clean-worktree baseline pytest result.
- Run focused tests for every new module and the existing named suites after each slice.
- Capture real app states (no seeded accounts): empty/needs-authentication/error/readiness views.
- Independent review of security-sensitive paths (auth status, credential refs, discovery URLs).
