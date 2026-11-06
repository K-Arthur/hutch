# Research plan (mandatory; do before design, record under docs/research/2026-11-vault-signin/)

Extend `docs/security/vault-and-authentication/research.md`; do not restart it. For each source:
URL, date accessed, the claim relied on, and what changed in the design. Reference pages from other
products are a feature checklist and a source of pitfalls; never copy their wording, names, or
behavior wholesale. If a page is gated by a CAPTCHA or anti-bot challenge, record it as
unreachable and use another source; do not try to get around it.

## A. Owner-supplied references (fetch every one)

- Hutch repository: https://github.com/K-Arthur/hutch (current README, issues, any security policy)
- https://rakazo.com/docs/self-host-storage/
- https://docs.x.ai/grok-bot/vault
- https://www.codync.dev/docs/artifacts
- https://www.codync.dev/docs/memory
- https://docs.openclaw.ai/gateway/authentication
- https://docs.openclaw.ai/auth-credential-semantics
- https://docs.openclaw.ai/gateway/secrets
- https://docs.openclaw.ai/gateway/secrets/runtime-model
- https://docs.openclaw.ai/gateway/secrets/secretref-contract
- https://docs.openclaw.ai/gateway/secrets/secret-store-and-egress
- https://docs.openclaw.ai/gateway/secrets/integration-examples
- https://docs.openclaw.ai/gateway/secrets/operations
- https://docs.openclaw.ai/gateway/1password
- https://docs.openclaw.ai/gateway/secrets-plan-contract
- https://docs.openclaw.ai/gateway/trusted-proxy-auth

For each, extract: the secret reference model, resolution timing (startup snapshot vs on use),
what happens on provider failure, egress mediation, audit, operations (reload, rotate, plan/apply),
trusted-proxy rules and their stated pitfalls. Compare with `vault/refs.py`, `vault/egress.py`,
and `server/security.py` and list concrete differences, adopt or reject with a reason.

## B. Standards and primary guidance (cite the current revision)

- WebAuthn Level 3 (user verification, `userVerification` and `residentKey` semantics, PRF
  extension for deriving a vault key from a passkey, and its real browser/authenticator support
  today; decide whether PRF-unlock is worth a later phase, do not ship without evidence).
- FIDO Alliance guidance on synced passkeys and recovery; OWASP ASVS (V2, V3, V6, V8),
  OWASP Authentication, Session Management, Password Storage, Cryptographic Storage, Secrets
  Management, and Logging cheat sheets; NIST SP 800-63B-4 (authenticators, reauthentication,
  session lifetimes); RFC 9449 only if OAuth token binding becomes relevant.
- Current guidance on Argon2id versus scrypt and whether `cryptography` or the stdlib now gives
  Argon2id without a new dependency (re-test decision D1; if it changed, propose, do not switch
  without asking).
- Browser behavior: Chromium virtual authenticator docs for Playwright; Clipboard API limits;
  autofill heuristics for `autocomplete` tokens; bfcache and `Cache-Control: no-store`.

## C. Comparable products (how each models secrets for agents and humans)

1Password (CLI `op`, service accounts, Connect, SDK, Agent hooks and any "secrets for agents"
work), Bitwarden (CLI, Secrets Manager), HashiCorp Vault and OpenBao (leases, response wrapping),
Doppler, Infisical, Akeyless, AWS Secrets Manager, Azure Key Vault, Google Secret Manager,
Docker secrets, Kubernetes secrets, systemd credentials, macOS Keychain, Windows Credential
Manager and DPAPI, Linux Secret Service/libsecret/KWallet, `age`/`sops`. Agent platforms:
OpenClaw, OpenCode, Claude Code, Codex CLI, Gemini CLI, Cursor, Cline, Roo, Continue, Aider,
Open WebUI, LibreChat, n8n credentials, Zapier/Make connection stores, Home Assistant secrets,
Browserbase and browser-agent credential handling, MCP authorization spec and its credential
guidance.

## D. Failure and complaint mining (equally mandatory)

Sources: GitHub issues and discussions for the products above, Reddit (r/selfhosted,
r/LocalLLaMA, r/1Password, r/Bitwarden, r/opsec, r/ClaudeAI), Hacker News, vendor forums, CVE and
GHSA advisories for agent tools and password managers, security blogs and conference talks on
agent secret exfiltration and prompt injection, incident write-ups on leaked API keys from agent
transcripts, logs, and shared screenshots.

Capture recurring complaints and classify each fixable-in-Hutch, mitigable, or vendor-side, with a
test idea for each fixable one. Required themes: see "Research requirements" in the master prompt
and the tables in `03-EDGE-CASES.md`. Also look specifically for:

- vault or keychain integrations that hang, prompt repeatedly, or break headless;
- unlock/biometric fatigue that pushes users to disable locking;
- "secret manager" features whose real egress was unmediated and so protected nothing;
- Bitwarden/1Password CLI session-token leakage via env or process list;
- passkey enrollment dead ends and recovery stories users call unacceptable;
- trusted-proxy/header-spoofing advisories and the mitigations that actually held up.

## E. Output

1. `01-SOURCES.md`: table of sources (URL, date, relied-on claim, effect).
2. `02-FAILURES-AND-COMPLAINTS.md`: clustered complaints, classification, test idea, requirement id.
3. `03-LESSONS-AND-DECISIONS.md`: adopted, rejected with reason, deferred with unblocker; each
   adopted item is a requirement id (`VS-R1`...) referenced by later phases and tests.
4. A short list of decisions that need the owner, batched into `02-PROGRESS.md`.

