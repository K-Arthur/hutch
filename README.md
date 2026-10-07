# OpenBot

> Your bots. Your machine. Your rules.

OpenBot is a **local-first, open-source multi-bot agent platform**. Run multiple named AI bots on
your own machine — each with its own model, tools, schedule, memory, and sandboxed workspace —
with human approval gates, hard spending caps, and complete run transcripts.

Cloud agent platforms (OpenAI Dots, Grok Team Bots, Meta Muse) rent you a black box with usage
limits. OpenBot inverts that: the orchestrator, the memory, the logs, and the bots are all yours,
on your hardware, with any model — local (Ollama, llama.cpp) or hosted (OpenAI and any
OpenAI-compatible API).

**Status:** early MVP under active development. See [docs/roadmap.md](docs/roadmap.md).

## Why

Every design decision answers a documented failure of existing agent products — surprise bills,
silent missed schedules, agents that escape their workspace, permission fatigue that drives people
to disable permissions entirely. See
[docs/research/complaints.md](docs/research/complaints.md) for the cited incident research, and
[docs/safety.md](docs/safety.md) for how OpenBot addresses it.

## Quickstart (once CLI ships)

```bash
uv tool install -e .          # or: pipx install -e .
openbot init                  # create state DB + starter bot templates
openbot serve                 # dashboard at http://127.0.0.1:8787
```

## License

MIT — see [LICENSE](LICENSE).
