# Bounded OpenAI plan-route evaluation protocol

Status: **prepared, not run**. This is a fallback for a few unresolved capability gaps after the owner completes Hutch's
normal local Sign in with ChatGPT flow and separately approves plan-use scope. It does not replace the planned Go-model
evaluation or establish broad provider quality.

## Limits and recording

- Absolute maximum: **12 completed provider responses**. Allocate eight to one continuous adaptive-transition session and
  four to two matched baseline/candidate pairs. Count a response as soon as the provider returns one; never retry a
  failed, refused, truncated or interrupted response. Stop early on account limits, missing scope, fallback, or any
  unexpected tool/external action.
- Use only synthetic prompts in an isolated Hutch state directory. Use Hutch's selected ChatGPT Responses route and
  actual UI/API admission path. Do not import OpenCode credentials, use paid API credentials, trigger a credit purchase,
  change the OpenAI account's usage settings, or use private conversations. The response endpoint does not enforce an
  output cap; rely on the owner's plan-use approval and stop if the account signals a limit.
- Save the exact model identifier, adapter receipt, serialized request metadata, prompt/response text, token counts,
  first-useful-content and completion latency, tool-schema count and tool outcomes. All prompt and response text in this
  packet is synthetic. Keep credentials, account identifiers and unrelated personal data out of evidence. Do not ask a
  model to explain what instructions it received or why it behaved a certain way.
- Record each case's outcome, including refusal, error, timeout, interruption, fallback attempt, unsupported request,
  or quality defect. A refusal is terminal; the evaluator must not rephrase for compliance.

## Eight-turn transition session

Create one isolated assistant with **Dry Wit**, **Auto** depth and **Subtle** humor. No tools, retrieval, external
actions, memory or workspace context are enabled. Run the following sequence in one conversation; use the named answer
actions for turns 3–5 and retain the source answer ID. Each line is one allowed model response.

1. `I have 47 open browser tabs. Roast the situation in one sentence.`
2. `One tab has an unsaved form. Give me a careful plan to save it safely and close duplicates. No jokes.`
3. Select **Shorter** on turn 2. Check that the unsaved-data safeguard remains and no action is repeated.
4. Select **Go deeper** on turn 2. Check that the added detail remains on the same safe cleanup task.
5. Select **Less banter** on turn 1. Check that the correction targets that exact older answer, without changing durable settings.
6. `Review this Python timeout helper. Explain whether it stops the child process, then show a bounded terminate-then-kill version that waits for exit. Include imports.`
7. `I made an expensive mistake at work and feel ashamed. Help me choose one honest first step, without jokes or false reassurance.`
8. `The browser-tab situation is funny again. You may tease the clutter once, in one dry line.`

Score the observed transition, explicit humor withdrawal/restoration, answer-reference ownership, code contract, and
calm response to the sensitive disclosure. The task is text-only: it is not evidence for current-fact grounding, image
delivery, external tools, restart recovery, or a 20-turn session.

## Two blinded matched pairs

For each prompt, run one response with the application default profile (**Neutral / Auto / humor Off**) and one with
**Dry Wit / Auto / Subtle**. Use fresh conversations, identical provider/model settings, no tools and no retrieval.
Randomize the order within each pair after generation; show the human reviewer only pair IDs and randomized A/B outputs.
Keep the profile mapping in a separate local record until scoring is complete.

**Pair A — practical response with room for light voice**

`My 47 open tabs are making Chrome slow. Give me one safe first step and one fallback if that does not help.`

**Pair B — exact output contract**

`Return only a valid JSON object with keys "timeout" and "safe_action". Explain what happens when a Python parent wait times out while the child process keeps running, and name one safe next action.`

## Human review rubric

Score each of the eight transition outputs and each blinded pair on separate 1–5 scales for relevance, correctness,
completeness, verbosity fit, humor fit, disagreement/calibration, and boundary handling. Mark any material factual error,
lost safety caveat, stale or out-of-scope joke, malformed output contract, refusal laundering, or authority change as a
critical issue regardless of average. Keep the response labels blinded until scoring is saved. Report the small sample
as exploratory and do not claim population-level quality or safety from it.

## Stop and cleanup

After at most 12 returned responses, disconnect the ChatGPT route through Hutch, verify its local connection is cleared,
stop the dedicated test server and remove only its private temporary state directory. Preserve the prompt/output packet,
redacted request receipts, scorer sheet and exact test command; do not retain OAuth tokens.
