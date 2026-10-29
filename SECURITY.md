# Security Policy

Hutch runs local agents with real tool authority. Reports about sandbox escapes, approval
bypasses, path or SSRF guards, credential handling, injection through untrusted tool or
retrieved content, and disclosure of local state matter during the development preview.

## Reporting a vulnerability

Report privately. Do not open a public issue for a security vulnerability.

- Preferred: use GitHub private vulnerability reporting for this repository: open the
  **Security** tab, then **Report a vulnerability**. This creates a private advisory that
  only the maintainer can see.
- Alternative: email **hello@kevinarthur.design**.

Include what you did, what happened, what you expected, the host details (OS and sandbox
primitives such as bubblewrap), and the exact version or commit (`hutch version`, or the
commit hash for a source checkout).

Do not attach transcripts, state-directory contents, credentials, snapshots, or other
sensitive data to a report. Describe them instead.

Acknowledgement and assessment are best effort by a solo maintainer during the development
preview. There is no published response-time commitment and no security SLA.

## Supported versions

Hutch is a development preview. The MIT-licensed source is public at
[github.com/K-Arthur/hutch](https://github.com/K-Arthur/hutch). Tagged source snapshots may be
published for the preview, but there are no packaged desktop installers and no hosted service.
The versioned source is 0.1.0, and fixes land on `main`. Treat the latest `main` or the newest
tagged source snapshot as the supported version; no older version is maintained under a support
policy.

## Scope notes

- Reports about third-party components (model providers, the OpenCode CLI, Playwright and
  Chromium, OAuth providers) are still useful, but Hutch can only fix its own boundary
  around them.
- Hutch's safety model and its honest limits are documented in [docs/safety.md](docs/safety.md).
  A mismatch between that document and actual behavior is itself a valid report.
- No independent security audit is on record for this project. The product does not claim
  to be secure, and the optional Linux sandbox is not a virtual machine. See the
  [containment review](docs/research/security-containment-2026-10-11.md).

## Local data

Hutch state (transcripts, memory, workspace files, database snapshots) is unencrypted local
data owned by the operator, as stated in the README and docs. Treat it as sensitive when
diagnosing any issue. Level of protection depends on your own operating system account,
disk encryption and backups.
