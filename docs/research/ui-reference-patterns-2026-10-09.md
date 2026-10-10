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
