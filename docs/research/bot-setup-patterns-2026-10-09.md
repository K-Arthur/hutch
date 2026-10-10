# Bot setup patterns and failure reports (2026-10-09)

## Scope and evidence

This review informs Hutch's create-a-Bot flow and large-roster navigation. Product
documentation is primary evidence for what each service says it supports. Forum and
Reddit posts below are individual reports from early adopters; they are useful as
failure scenarios, not evidence of how common a problem is. Hutch has not connected
to these products or accounts as part of this review.

## Patterns worth adapting

**Grok Bot** frames a Bot as a teammate with a name and one ongoing job. Its current
setup docs start from a described responsibility and then let the owner fill out a
profile; its quick-start examples put a concrete outcome and constraints into chat.
The product also supports creating or hiding focused Bots from chat and pinning
frequent ones. The helpful lesson is to begin with a request the owner already wrote
and only add a separate Bot when work needs a distinct role or access boundary.
[Get started](https://docs.x.ai/grok-bot/get-started),
[create and manage Bots](https://docs.x.ai/grok-bot/bots),
[overview](https://docs.x.ai/grok-bot/overview).

**OpenAI Dots** starts with one primary Dot. Owners describe a goal, share context,
and continue talking while it works; setup includes naming and connecting selected
apps. Its official guidance distinguishes a conversation from an ongoing
responsibility, puts activity and pause controls in the Dot profile, and treats
connected apps, messaging channels and computer access as different grants. The
launch announcement describes specialist Dots as a future direction, not a generally
available capability. Hutch should therefore keep the user-named workspace
coordinator as the easy starting point and present specialists as optional,
owner-approved workers. [OpenAI Dots announcement](https://openai.com/index/introducing-dots/),
[official getting-started and controls guide](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot),
[Dots product guide](https://learn.chatgpt.com/docs/dots).

**GPT Builder** is a separate, useful configuration reference. Its current guide
offers a conversational builder alongside direct field editing, then a Preview for
testing before save and version history for restoring earlier configurations. Those
are good progressive-disclosure and change-review patterns. Availability is
currently limited by account/workspace policy, and the same official help article
now says custom GPTs are planned for retirement in favor of Plugins. We should borrow
the interaction patterns rather than make GPTs a long-term compatibility promise.
[Creating and editing GPTs](https://help.openai.com/en/articles/8554397-creating-and-editing-gpts).

## Reported failures to design against

- A Grok Bot business user reported daily browser-profile resets, frequent browser
  crashes, only one or two simultaneous workers, and usage falling faster than
  expected while running six Bots. This is one heavy user's account, not a measured
  service-wide rate. Hutch's acceptance cases should preserve per-Bot browser
  profiles, verify profile cleanup/recovery, measure concurrent admission, and show
  estimated versus measured usage and uncertainty. [Individual report](https://www.reddit.com/r/grok/comments/1vob5q2/grok_bot/).
- A Cursor support report says a configured “Always allow” local execution setting
  still failed with an unapproved message and no approval card. The product lesson
  is that permission settings, decisions, and visible prompts must resolve to one
  authority and a user-visible state. [Support bug report](https://forum.cursor.com/t/grok-bot-externalshell-blocked-despite-always-allow/168180).
- An early Dots user reported messages staying at “read” with no response and the
  Dot temporarily disappearing. This is an anecdotal outage report. Hutch should
  retain explicit queued/running/failed/offline states and actionable retry or
  reconnect guidance instead of letting a sent message look like a completed run.
  [Individual report](https://www.reddit.com/r/OpenAI/comments/1wxh6ky/anybody_elses_dot_completely_broken/).
- A Dots user objected to not being able to inspect, edit or selectively delete
  individual agent memories or precisely control cross-domain sharing. OpenAI's own
  help says a Dot's saved memories are removed by deleting the Dot, and disconnecting
  an app does not delete information already obtained. This request is anecdotal,
  but the control gap is also described by the vendor docs. Hutch keeps scoped facts
  reviewable, editable, exportable and explicitly shareable; conversation history,
  facts, project files, receipts and secrets remain separate.
  [User report](https://www.reddit.com/r/OpenAI/comments/1wx8x9q/why_i_will_not_use_dots_insufficient_visibility/),
  [official memory and app controls](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot).
- A Grok Bot user reported uncertainty that additional specialist Bots justified the
  usage consumed; another reported hitting a weekly limit mid-week. These posts are
  not a sample of all users. They support Hutch's small-by-default roster, explicit
  workspace defaults and shared budget reservations, and they argue against
  creating one Bot per ordinary chat request. [Usage report](https://www.reddit.com/r/GrokBot/comments/1wxwvu9/usage/).

## Hutch implementation decision

The default **New Bot** path reuses the latest user request in an active chat as the
starting instructions; **Make a bot** binds the exact selected message. Users review
the request and a professional name without re-entering the work, and may edit the
instructions if needed. An empty chat asks for a new responsibility. The path reuses
the validated workspace model default (or the exact selected chat Bot route where
applicable), suggests an editable name locally, and exposes the safe starting settings
before one **Create bot** action. It creates no run, adds no tools, schedule,
connection, credential or permission, and uses ask-first action approval. When no
model route is configured, the user is sent to the model step; there is no silent
provider fallback.

An explicit **Customize** action preserves the existing model/workspace, tools,
memory, schedule, limits, browser handoff, import and review flow. Prompt refinement
stays opt-in and review-only. Large rosters collapse idle, unpinned Bots after ten
total Bots; the coordinator, pinned Bots, active or waiting Bots, and the current
chat remain directly visible. Search and a keyboard-operable disclosure retain full
access to the rest.

These choices shorten routine setup without hiding authority choices. They do not
make all coordinator conversations into Bots, create specialist Bots automatically,
or imply that an installed app has been connected.
