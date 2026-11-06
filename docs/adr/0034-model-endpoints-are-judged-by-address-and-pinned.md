# ADR-0034: Model endpoints are judged by the address they reach, and the connection is pinned to it

Status: accepted, 2026-11-06.

## Context

Phase 5 of the provider expansion looked at custom and local endpoints. A real LM Studio server on loopback and the
code showed (research record `docs/research/2026-11-provider-expansion/06-LOCAL-AND-CUSTOM.md`):

- `https://169.254.169.254/v1` was accepted as a connection endpoint; only plain HTTP was refused, and only by a rule
  about the scheme.
- A bot's `base_url`, `OLLAMA_HOST` and `HUTCH_BASE_URL` routes accepted any URL, including plain HTTP to a public host,
  and sent `HUTCH_API_KEY` over it.
- A name was never judged by what it resolved to, so a public-looking name that resolves to loopback or a LAN address
  was trusted (DNS rebinding; the reason NCC Group's CVE-2024-28224 advisory exists for Ollama).
- A connection test reported the wrong layer: "cannot connect - is the server running?" for HTTPS against a plain-HTTP
  port, and "invalid model catalog" for a URL that only lacked `/v1`.

OpenClaw's guarded-fetch rules (exact-origin trust, metadata and link-local never allowed, fake-IP ranges only for the
configured host) were used as a feature checklist, not copied.

## Decision

1. One module, `providers/endpoint_policy.py`, classifies an address as `loopback`, `private` (RFC 1918, ULA,
   100.64.0.0/10), `fake_ip` (198.18.0.0/15), `public` or `blocked` (link-local including cloud metadata,
   unspecified, multicast, reserved, documentation and tunnel ranges). `blocked` is refused for every scheme, for IP
   literals in every spelling the operating system accepts, and for any name that resolves to it.
2. A name may resolve to loopback or private only if it is local-style (`localhost`, a single label, `.lan`, `.local`,
   `.home.arpa`, `.internal`, `.localdomain`, `.ts.net`), is listed exactly in `HUTCH_PRIVATE_HOSTS`, or is a vendor host
   a template declares. Otherwise it must resolve to public or fake-IP. The refusal states the fix.
3. `providers/pinned_transport.py` resolves once per request, judges every answer, and connects to the validated
   numeric address with the original `Host` header and TLS server name, trying the validated addresses in resolver
   order. It is installed at the one seam every httpx adapter already uses, `offline.httpx_offline_options`, outside
   Strict Offline (which keeps its broker). With an environment proxy the address cannot be pinned; literals are still
   checked. The Anthropic SDK uses a different HTTP stack here, so its custom endpoints get a check before each call,
   not a pin.
4. Plain HTTP goes only to loopback or private addresses, and a credential header is never sent over plain HTTP off
   loopback. Redirects are still not followed.
5. At save, blocked literals and metadata names are refused for every scheme, and a pasted API path
   (`/chat/completions`, `/models`, `/messages`, `/v1/messages`) or trailing slash is reduced to the root. Nothing is
   ever appended: whether a server wants `/v1` is for the connection test to report.
6. `providers/endpoint_probe.py` walks address, DNS, connect, TLS, key and model list in order, stops at the first
   failure and says what it means; it makes no inference request. `check_connection` uses it only after the provider's
   own check failed. After a success on a custom endpoint it makes one keyless `GET /api/version` to name Ollama from its
   own answer and warn that `/v1` cannot set its context window. A custom endpoint's result is reported as not
   key-verified, because a user-run server answers its model list with any key or none.
7. vLLM and SGLang publish `max_model_len` on every `/v1/models` entry. It is the applied window only when `owned_by`
   names the server; any other OpenAI-compatible server stays unknown.

## Consequences

- A bot or connection that relied on a public-looking name resolving to a private address now fails with an explicit
  message until the name is listed in `HUTCH_PRIVATE_HOSTS` or replaced by the address. That is the deliberate boundary
  change; local-style names and IP literals are unaffected.
- Every provider request does one resolver lookup. Vendor hosts keep working when DNS is split-horizon; only `blocked`
  applies to them.
- Self-signed certificates stay refused. `SSL_CERT_FILE` is honored; no switch skips verification.
- A name that fails to resolve is reported as the DNS layer, not as a dead server.
- Not changed: keyless named connections (the keyless route is `vllm/<model>` or `openai-compatible/<model>` with the
  bot's base URL, now guarded), Strict Offline, and the approval model.
