# Onboarding 2026-10: research record

The actionable research document is
[docs/research/onboarding-and-getting-started-2026-10.md](../../research/onboarding-and-getting-started-2026-10.md).
This file records how it was produced and what was not verified.

## Commands and sources used (2026-10-30)

- Rendered text of the OpenClaw getting-started, onboarding-overview, wizard and
  onboarding pages, the Grok Bot get-started and bots pages, and the MausBot
  download page was fetched over HTTP and read (all returned 200).
- GitHub issues API: search plus direct reads of openclaw/openclaw #1818, #2697,
  #27009, #32828; anomalyco/opencode #54833; openai/codex #2798, #48237;
  anthropics/claude-code #34229.
- Web searches (summaries only): OpenAI Dots, n8n onboarding, NN/g progressive
  disclosure, Ollama requirements, OpenCode authentication persistence.

## Not verified

- Reddit and Hacker News threads were not opened. No claim depends on them.
- OpenAI Dots documentation was not opened at the vendor origin; its row is
  low-confidence orientation.
- Search-summary figures for Ollama model sizes are indicative; the local-service
  step must read real sizes from the running service rather than quote them.
- Issue reaction counts are anecdotal, not prevalence.

## Inherited evidence

The earlier catalog in `docs/onboarding/research.md` (27 comparable failure rows,
standards references) is reused, not repeated.
