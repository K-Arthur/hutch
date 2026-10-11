# Response style and answer feedback

Response style changes how an assistant words a reply. It does not change which tools it can use, what it may access, whether a person must approve an action, or how much work a request needs.

## Choose a style

In assistant settings, choose a voice preset, answer depth, and humor level independently. Direct, Warm, and Dry Wit set the voice. Auto, Brief, Standard, and Detailed set the amount of explanation. Off, Subtle, and Playful set the humor allowance; humor still depends on the current request being clearly playful and suitable for it. The legacy `thorough` value remains readable as Detailed.

Optional warmth, directness, formality, profanity, format, and avoid-habit controls use bounded choices. Profanity stays off unless explicitly changed. Existing users do not gain humor or profanity just because the new controls are available.

An unset choice inherits in this order: the current turn, the conversation, your saved style for that assistant, the assistant's preset, then Hutch's default. Choose **Inherited** to remove an override and return to that chain. Assistant and conversation edits use revisions; if another tab saves first, Hutch reloads the current version and keeps your edits for review before you try again. A next-reply override applies to one message and stays in that browser's conversation state until it is sent or cleared.

Controls are not previews: changing them makes no model request. Examples are labeled separately. Any live preview must be explicitly requested, use isolated state, and show its usage budget before it runs.

## Correct or rate one answer

On a completed built-in answer, **Shorter**, **Go deeper**, and **Less banter** ask for a new response based on that selected answer. They do not rerun tools or external actions. Review the new response as new work; the rewrite does not make an earlier claim fresh evidence.

The **Helpful** and **Needs work** controls save a rating for that specific answer. A Needs work rating can include one fixed reason: accuracy, relevance, completeness, depth, tone or humor, safety or boundaries, or other. The reason is optional, and the owner can clear a rating. Feedback is stored in Hutch's local SQLite state, is excluded from conversation exports, and is not sent to a model. It does not update a saved response style, train a model, or infer durable preferences. The answer metadata exposes a monotonically increasing revision so conflicting edits can be detected; only the current rating is kept.

Correction and feedback controls are currently limited to completed answers from Hutch's built-in runtime. Pi and OpenCode Bot execution remain disabled; their absence from these controls does not enable either adapter.

## Privacy and limits

Saved assistant and conversation styles, response-plan snapshots, and local answer feedback are held in Hutch's state database. Run snapshots can appear in local run records. If a hosted model handles a normal reply or rewrite, its prompts and answer references follow that provider's data-handling terms. A correction makes a provider request; rating feedback does not. Conversation exports include message text and provenance but exclude answer feedback and response-style preferences. Review message text before sharing an export.

Persona instructions are guidance, not provider-enforced guarantees. They cannot override safety rules, factual grounding, requested formats, evidence, permissions, approvals, recipients, spending limits, code requirements, or artifact voice. Sensitive and consequential requests remain plain and steady, and explicit corrections or withdrawn teasing consent apply to the current turn.

See [the architecture notes](architecture.md#response-style-and-answer-feedback) for the run-plan and persistence contract and [the safety model](safety.md#response-style-does-not-set-authority) for authority boundaries.
