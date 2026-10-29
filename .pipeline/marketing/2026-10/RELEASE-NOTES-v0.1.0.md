# Hutch v0.1.0 (development preview, source tag)

This is the first tagged source snapshot of Hutch, a local-first platform for
personal AI assistants that run on your own Linux computer. It is a development
preview: behavior, storage schema and command-line interfaces can change between
commits.

## What this tag is

- A source snapshot of the public repository. There is no packaged desktop
  installer, no hosted sign-up and no PyPI package.
- MIT-licensed. The software is free; hosted model use is billed by the
  provider account you configure.
- Linux-first. macOS and Windows executor support is not implemented.

## What is in it

Named assistants with their own model, tools, schedule, memory and workspace;
ask-first approvals and hard-denied shell command classes; estimated spend
ceilings and usage reservations with provider billing named as authoritative;
locally stored, hash-verified run transcripts; recurring tasks with IANA
timezones that catch up after sleep; local or hosted model routes; and an
evidence ledger recording what works, what is experimental and what is
unavailable.

## Try it

```bash
git clone --depth 1 https://github.com/K-Arthur/hutch.git
cd hutch
uv sync --extra dev
uv run hutch init
uv run hutch serve   # http://127.0.0.1:8787
```

Configure a real model route in Apps & AI before starting a run. The full
quickstart, availability table, hardware and provider limits, and known gaps are
in the README and docs.

## Known limits

- Development preview, Linux only, no installers, no hosted service.
- A model route you configure is required; live paid-provider checks are not
  performed for this preview.
- Experimental and unavailable areas are labelled in the README availability
  table and docs/realignment/ledger.md.
- Usage estimates are not provider-enforced spending limits.
- Hutch is not a virtual machine and makes no security guarantees; the safety
  model and its limits are in docs/safety.md.

Report security issues privately per SECURITY.md, not in a public issue.
