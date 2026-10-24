# Security

## Reporting a vulnerability

Hutch runs local agents with real tool authority, so reports about sandbox escapes, approval
bypasses, path/SSRF guards, credential handling, injection through untrusted tool or retrieved
content, and disclosure of local state matter even in a private preview.

- Report privately by email to **hello@kevinarthur.design**. Do not open a public issue.
- Include what you did, what happened, what you expected, the host details (OS and sandbox
  primitives such as bubblewrap), and the exact version or commit (`hutch version`).
- Do **not** attach transcripts, state-directory contents, credentials, snapshots, or other
  sensitive data to a report — describe them instead.
- Acknowledgement and assessment are best effort by a solo maintainer during a private preview;
  there is no published response-time commitment.

## Supported versions

There is no public release: no tags, no package, no hosted service. "Supported versions" is
therefore any commit of `main` in a private source checkout; fixes land on `main`.

## Scope notes

- Reports about third-party components (model providers, the OpenCode CLI, Playwright/Chromium,
  OAuth providers) are still useful, but Hutch can only fix its own boundary around them.
- Hutch's safety model and its honest limits are documented in [docs/safety.md](docs/safety.md).
  A mismatch between that document and actual behavior is itself a valid report.

## Local data

Hutch state — transcripts, memory, workspace files, database snapshots — is unencrypted local
data owned by the operator, as stated in the README and docs. Treat it as sensitive when
diagnosing any issue.
