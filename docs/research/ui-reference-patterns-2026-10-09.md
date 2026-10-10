# UI reference review and access record (2026-10-09)

This is the starting record for the standing UI research workflow: consult
Mobbin for web and mobile references and Figma Community for relevant screen
systems before each frontend slice. Hutch's user-provided Grok Bot screenshots
and [`DESIGN.md`](../../DESIGN.md) remain the product-specific direction; outside
work is evidence and inspiration, not a visual authority.

## Mobbin

I opened the public [Mobbin site](https://mobbin.com/) and queried the connected
Mobbin MCP for an AI assistant workspace screen on web and an assistant inbox on
iOS. Both screen searches returned the same access response: **Mobbin MCP
requires a paid plan**. The public Mobbin page also labels its agent/MCP access
as Pro and Team. I did not bypass the plan gate, purchase access, or claim to
have inspected Mobbin screens. This remains an access limitation for the next
frontend pass.

## Figma Community

The authenticated Community search for “AI chatbot app” returned the free
[BrainBox AI ChatBot Mobile App UI Kit](https://www.figma.com/community/file/1316069776447695879/brainbox-ai-chatbot-mobile-app-full-100-free-ui-kit).
Its public cover is a contact sheet of many mobile screens in light and dark
themes. I inspected that cover, but its individual screens are too small to
evaluate; it is a discovery lead, not a usable component or layout specification.

The [Bobo Chatbot Messenger App UI Kit](https://www.figma.com/community/file/1216056004395666907/bobo-chatbot-messenger-app-ui-kit)
is listed at **$29**. Its public cover shows a mobile conversation list,
conversation examples, and a welcome screen with a bright teal robot. The
underlying file and individual frames were not opened, and no purchase was made.
Those motifs are not a fit for Hutch's restrained 2D operator mascots or its
owner-controlled, conversation-first workflow.

For the web marketing surface, I inspected the public cover of the free
[AI Agent Builder / Flowise landing page](https://www.figma.com/community/file/1516734333826282749/ai-agent-builder-landing-page-website-designs-free-website-templates-web-design-inspiration).
Its description targets a developer builder and its cover uses a purple neon
palette and dense product mockups. That may fit a developer tool launch page,
but is a poor fit for Hutch's existing emerald design language and clarity-first
product story, so its style was not adopted.

## Decisions applied to Hutch

- The main-branch operator design is the source of truth: 8px controls, 12px
  panels, 18px chat surfaces, emerald actions, azure focus, and monochrome status
  labels with an icon or word. Server-rendered pages and the public site are being
  brought into that shared geometry and semantic palette while keeping the
  marketing layout, Archivo display typography, and 3D hero art.
- Bot names generated from a user request stay concise. Owners can edit them;
  long custom names are clamped to two lines in the roster while the full name
  stays in the accessible control text and title.
- The user-provided Grok Bot screenshots remain the better product reference for
  named Bot conversations, simple list identities, inline human decisions,
  handoff, and direct setup from existing chat context.
- Future UI work records the exact references and inspected viewports. When a
  reference library or preview is inaccessible, that boundary is stated and the
  product is validated against local screens, keyboard behavior, and responsive
  fixtures instead.

These sources have not been used as a replacement for Hutch usability testing;
reference popularity and creator descriptions do not establish that a pattern
works for Hutch users.

## Bot and conversation overflow actions (2026-10-09)

The user's supplied Grok Bot screenshots show a single overflow menu with
conversation actions such as unread, pin and section, while Bot actions include
hide and template sharing. Current official Grok Bot guidance also documents
duplicating a Bot as a starting point, pinning active Bots, recoverable hide,
manual unread state and per-Bot notifications. Its duplication behavior copies
profile/settings/routines but omits chat history, learned memory and attachments.
Hutch adopts the compact menu and recovery cues, but deliberately makes Bot
duplication safer for Hutch's permission model: it carries forward role
instructions, model route, inference mode, workspace type and limits into a
reviewable draft while requiring the owner to reselect tools and any account
access. It does not copy schedules, memory values, credentials, external URLs,
folder paths, browser handoff or chat history. A duplicate does not start work.
[Grok Bot management](https://docs.x.ai/grok-bot/bots),
[Grok Bot settings and notifications](https://docs.x.ai/grok-bot/settings-and-notifications).

Open WebUI's current conversation-organization guide uses pin/folder/unread
state and recovery for archived chats. Its 2026 issue #28135 reports a visible
"Mark as unread" action that did nothing in search because that menu consumer
did not provide a handler. This single issue is not evidence of prevalence; it
is a useful acceptance scenario. Hutch therefore tests server persistence,
idempotent replay, unread clearing on reopen, keyboard focus return, and archive
restore rather than checking that menu labels merely render.
[Conversation organization](https://docs.openwebui.com/features/chat-conversations/chat-features/conversation-organization/),
[reported inert unread action](https://github.com/open-webui/open-webui/issues/28135),
[sidebar state and clarity discussion](https://github.com/open-webui/open-webui/discussions/27269).

The same product's Workspace guide documents reusable prompt templates with
typed variables, slash-command insertion, and JSON import/export. The user's
Grok screenshot adds a compact menu hierarchy: keep organization actions easy
to reach and put sharing/hide/other less frequent actions behind one menu. Hutch
now has a local saved-request library that can be searched, edited, deleted, and
inserted into a draft from any chat. Saving reviews only the first user request;
using a saved item never submits it. The JSON download/import path remains for
intentional file portability. Typed placeholders and slash-command invocation
are deferred; a user can edit the filled draft before sending, which avoids
introducing another syntax to discover or a template-driven automatic action.

Grok Bot documentation offers public or team-only Bot-template links and warns
that identity, description, skills, and routines are visible in the shared
configuration. Hutch has no tenant-aware sharing controls. Reusable requests
therefore stay in Hutch's local SQLite state and backups; a template JSON file
is downloaded only after review, and Hutch exposes no public link. This also
avoids adding a duplicate **Hide** action to chat history: Hutch's existing
recoverable Archive/Restore path removes a chat from active recents and keeps it
available in the archived group.
[Open WebUI Workspace prompts and import/export](https://docs.openwebui.com/features/workspace/),
[Grok Bot templates and sharing scope](https://docs.x.ai/grok-bot/bots).

This is an incremental choice: import/export enables reuse while leaving template
storage local to the user's file system. A saved prompt library with typed inputs
would improve repeated work, but should be designed with explicit ownership,
backup, and migration semantics rather than silently stored in browser state.

The user-provided screenshot remains the interface reference for this slice.
Mobbin's connected screen search returned its paid-plan gate. The selected Bobo
Figma node rendered the full 32,128×20,200 canvas scaled to 1,200×755, and the
design-context tool reported that no individual layer was selected. Its tiny
contact sheet does not support component-level findings; no Figma elements,
assets, or tokens were copied. The implementation follows the user's screenshot
and Hutch's committed design tokens, while Mobbin/Figma detail access remains
unverified.
