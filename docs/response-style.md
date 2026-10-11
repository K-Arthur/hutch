# Response style and answer feedback

Response style changes how an assistant words a reply. It does not change which tools it can use, what it may access, whether a person must approve an action, or how much work a request needs.

## Choose a style

In assistant settings, choose a voice preset, answer depth, and humor level independently. Direct, Warm, and Dry Wit set the voice. Auto, Brief, Standard, and Detailed set the amount of explanation. Off, Subtle, and Playful set the humor allowance; humor still depends on the current request being clearly playful and suitable for it. The legacy `thorough` value remains readable as Detailed.

Optional warmth, directness, formality, profanity, format, and avoid-habit controls use bounded choices. Profanity stays off unless explicitly changed. Existing users do not gain humor or profanity just because the new controls are available.

An unset choice inherits in this order: the current turn, the conversation, your saved style for that assistant, the assistant's preset, then Hutch's default. Choose **Inherited** to remove an override and return to that chain. Assistant and conversation edits use revisions; if another tab saves first, Hutch reloads the current version and keeps your edits for review before you try again. A next-reply override applies to one message and stays in that browser's conversation state until it is sent or cleared.

Controls are not previews: changing them makes no model request. **See written examples** opens fixed, labeled Direct, Warm, Dry Wit, Brief and Detailed examples; these are authored text and do not use your selected model. **Preview this draft** is a separate, explicit model request. Before it can run, Hutch checks the assistant's local limits and shows a one-response estimate. The preview uses a fixed fictional sample and the current unsaved style, without conversation history, standing directions, tools, skills, or workspace access. It creates a standalone local run record but does not save the style. You can stop it while it runs. **Redacted request and timing** shows the resolved preview scope and saved-profile revision, serialized adapter shape, and Hutch-measured model/queue time. It omits prompt and response text, credentials, account details, provider endpoints, and hidden reasoning; serialization does not prove the provider accepted the request.

## Correct or rate one answer

On a completed built-in answer, **Shorter**, **Go deeper**, and **Less banter** ask for a new response based on that selected answer. They do not rerun tools or external actions. Review the new response as new work; the rewrite does not make an earlier claim fresh evidence.

The **Helpful** and **Needs work** controls save a rating for that specific answer. A Needs work rating can include one fixed reason: accuracy, relevance, completeness, depth, tone or humor, safety or boundaries, or other. The reason is optional, and the owner can clear a rating. Feedback is stored in Hutch's local SQLite state, is excluded from conversation exports, and is not sent to a model. It does not update a saved response style, train a model, or infer durable preferences. The answer metadata exposes a monotonically increasing revision so conflicting edits can be detected; only the current rating is kept.

Correction and feedback controls are currently limited to completed answers from Hutch's built-in runtime. Pi and OpenCode Bot execution remain disabled; their absence from these controls does not enable either adapter.

## Local rollback

The local operator can disable the adaptive response-style feature at startup with
`HUTCH_ENABLE_ADAPTIVE_PERSONA=0` (also accepts `false`, `no`, and `off`). The default is enabled; accepted
enabled values are `1`, `true`, `yes`, and `on`. Restart Hutch after changing the variable. When disabled,
assistant and conversation profiles remain readable and are not rewritten or deleted. Settings and next-reply
controls become read-only, the preview budget reports unavailable, and Hutch rejects profile edits, previews,
answer rewrites, and feedback with a clear conflict response. New runs do not resolve or apply a persona plan,
and low-risk banter keeps its normal task route. A run that already captured a plan keeps that write-once plan
if it must recover. Re-enabling the feature restores the saved preferences without a migration or reset.

## Privacy and limits

Saved assistant and conversation styles, response-plan snapshots, and local answer feedback are held in Hutch's state database. Run snapshots can appear in local run records. A live preview record contains the fixed sample, candidate style and model response; it is not attached to a conversation. The built-in runtime permits one non-streaming response up to the lesser of 128 output tokens or the assistant's configured per-turn limit, and does not fall back, escalate, or retry. Hutch blocks previews when a hosted model has no known Hutch price or when the route cannot enforce the output cap. Local models show no per-token Hutch charge; a flat provider allowance may still count. Hosted cost estimates are local estimates and provider billing can differ. When a hosted model handles a preview, normal reply, or correction, its prompt follows that provider's data-handling terms. A correction makes a provider request; rating feedback does not. Conversation exports include message text and provenance but exclude answer feedback and response-style preferences. Review message text before sharing an export.

Persona instructions are guidance, not provider-enforced guarantees. They cannot override safety rules, factual grounding, requested formats, evidence, permissions, approvals, recipients, spending limits, code requirements, or artifact voice. Sensitive and consequential requests remain plain and steady, and explicit corrections or withdrawn teasing consent apply to the current turn. A fixed preview sample does not test live response quality or provider adherence; human review is still pending.

See [the architecture notes](architecture.md#response-style-and-answer-feedback) for the run-plan and persistence contract and [the safety model](safety.md#response-style-does-not-set-authority) for authority boundaries.
