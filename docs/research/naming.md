# Research: project naming (Oct 2026)

The working name "openbot" was flagged as colliding with other active projects — confirmed:
`openbot` is **taken on PyPI**, and GitHub has multiple unrelated "openbot" projects. A rename
was required before any public push. Researched 2026-10-07.

## Method

1. **PyPI availability** — `pypi.org/pypi/<name>/json` must 404 (`pip install <name>` must install *us*).
2. **GitHub collisions** — same-space, starred projects make the name unsearchable.
3. **Web/marketing scan** — existing companies, movies, SEO battles.

## Candidates evaluated

| Name | PyPI | GitHub collision | Marketing notes | Verdict |
|---|---|---|---|---|
| openbot | **TAKEN** | multiple unrelated projects | — | rejected (the reason for renaming) |
| ownbot | TAKEN | — | — | rejected |
| **hitch** | TAKEN by test-framework bootstrapper **abandoned 2015** — the clean name is effectively squatted | `varnish/hitch` — 1,944★ actively maintained TLS proxy | 2005 Will Smith movie + hitchhiking dominate search | rejected: conflicts on all three fronts |
| hutch | **FREE** | `ruby-amqp/hutch` (876★) is Ruby/RabbitMQ message processing — different domain; `hutchdb` (15★) adjacent-but-small | "Hutch" mobile-games company exists, not in dev tools; a hutch is a home enclosure where you keep and care for animals — exactly the local-first supervised-bots metaphor | **CHOSEN** |
| botshed | FREE | none found (only 0★ unrelated repos) | clean SEO; "your bots live in the shed, not the cloud" | runner-up (fallback) |
| hatch | TAKEN — PyPA's project manager | — | — | rejected |
| latch | TAKEN (Latch/Door smart-locks, NASDAQ-listed) | — | — | rejected |
| clutch | TAKEN (clutch.co) | — | — | rejected |
| stitch | TAKEN (Singer/Stitch data pipelines) | — | — | rejected |
| botyard | FREE | `cheatsnake/botyard` (8★) "self-hosted chatbot platform" — same space | — | rejected |
| hivekeep | FREE | `MarlBurroW/hivekeep` (68★) "self-hosted platform of autonomous, persistent" agents — same space | — | rejected |
| woodshed | FREE | `gaearon/woodshed` (70★, Claude Skills tool) — same AI-tools space | — | rejected |
| botsmith | FREE | multiple same-space repos | — | rejected |
| roost | FREE | none significant | generic-word SEO (poultry) | not selected |
| apiarist / majordomo / menagerie / steward / errand / minder | all TAKEN | — | — | rejected |

## Decision

**hutch** — per maintainer preference for the short, warm sound (validated as the best
conflict-free option in that family), with `botshed` documented as the fallback if a
conflict surfaces before launch.

Brand usage: always lowercase — `hutch` (package, CLI, logo wordmark). Repository name at
push time: `hutch`. State directory: `~/.local/state/hutch`.

## Sound-alike family checked at the maintainer's request

hitch, hatch, latch, clutch, stitch, batch, patch, catch, botch, thatch, vetch — every viable
candidate is occupied on PyPI (or semantically wrong: `botch` means "to ruin badly").
`hutch` itself was free, which settled it.
