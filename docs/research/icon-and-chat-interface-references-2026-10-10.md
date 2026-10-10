# Icon and chat-interface references (2026-10-10)

This review informs the local Hutch interface. It does not establish market
prevalence, provider endorsement, or permission to reproduce third-party brand
artwork.

## Figma Community icon reference

I opened the individual [Lucide Icons Figma Community file](https://www.figma.com/community/file/1400832564720554478/lucide-icons),
published by Lucide, and checked its resource links and attribution rather than
using a collage or a search-result thumbnail as design evidence. The file links
to the Lucide and Feather projects and identifies a Creative Commons
Attribution 4.0 license for the Community resource. The upstream
[Lucide repository license](https://github.com/lucide-icons/lucide/blob/main/LICENSE)
is ISC, with MIT terms for its listed Feather-derived icons. Hutch does not
vendor SVGs from the Figma file in this change; the local interface follows the
consistent 24×24 outline, current-color, round-cap vocabulary as a reference.

The product uses OpenAI's exact, unaltered white Blossom beside the named
ChatGPT service. I also located the official full-color Outlook app icon. The
current [Microsoft Trademark and Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks)
say that Microsoft logos, app icons, and product icons cannot be used without an
express license; this repository records no such license. I therefore did not
bundle the Outlook icon. Microsoft Outlook appears by its full service name with
Hutch's own blue-toned inbox category glyph. This identifies the service
without presenting original Hutch artwork as a Microsoft logo.

I did not bundle Gmail or Google Calendar product icons. Google's official
[product list](https://about.google/brand-resource-center/products-and-services/)
links both services to general icon guidance. Its [brand guidance](https://about.google/brand-resource-center/guidance/)
says product-icon use may require a request; Google's Partner Marketing Hub
explains that an account is used to request permission. The detailed icon page
could not be retrieved in this review, so I cannot claim that every in-app
integration use requires approval. Hutch has no permission recorded and keeps
clearly labeled, original category glyphs until the terms for this use are
confirmed. OpenAI's [brand guide](https://openai.com/brand/) says not to add
colors to the Blossom; the app uses its exact local white mark only beside the
named ChatGPT service, not as Hutch's brand. The earlier Google SVG files came
from an older icon generation and have been removed; the current refresh is
documented by [Google Workspace Updates](https://workspaceupdates.googleblog.com/2026/05/introducing-fresh-visual-identity-for-Google-Workspace-app-icons.html).

## User-provided ChatGPT screen

The individual desktop screenshot supplied in this conversation shows a narrow
global navigation rail, distinct **Pinned**, **Projects**, and **Recents**
groups, a moderate-width conversation column, an assistant identity in the
conversation header, and a composer anchored at the bottom. Those patterns are
useful references for discoverability and reduced navigation clutter. Hutch's
assistant roster and workspaces have different behavior, so the screenshot is a
structural reference rather than a pixel-copy target.

The accompanying mobile references support keeping message-level actions near
the related assistant or conversation and keeping the active task visible in
the chat. Hutch retains explicit approval boundaries and provider/data-flow
disclosures; the visual reference does not establish those product behaviors.
The supplied conversation-list action sheet groups **Mark unread**, **Pin**,
**New section**, **Share as template**, **Hide**, and a **More** submenu in one
place. This supports Hutch's single overflow control per assistant or
conversation, with less common actions grouped instead of exposing a row of
separate buttons.

## User-provided assistant customization and device-access screens

The supplied customization screen was reviewed as an individual screen: one
large character preview, a clearly separated color row and character picker,
an editable assistant name, and one save action. It supports Hutch's direction
to make the simple 2D app character adjustable without exposing advanced setup
fields by default. The companion device-access screen puts connected devices,
connection state, recent activity, and outputs in distinct groups, with one
clear action for an unapproved device. Hutch should preserve that scan order and
show actual device/session state rather than copying the reference's labels.

These screenshots are task references, not evidence that Hutch already supports
those device operations or that a particular layout performs better for all
users. I individually selected and inspected the supplied Figma Community
file's [new-chat screen](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-66),
[conversation list](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-67),
[chat options menu](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-61),
and [settings screen](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-40)
one at a time on its canvas. Those screens reinforce short action menus, one
clear assistant identity, and grouped settings; the light UI kit is a pattern
reference, not a visual system to copy into Hutch. The native Mobbin searches
returned a paid-plan requirement, so no Mobbin results were used. Figma MCP
node retrieval also hit the connected account's Starter-plan limit; the opened
canvas remains available for visual reference.

## Decisions and validation limits

- Share locally bundled Archivo display typography, semantic colors, controls,
  and icon treatment across the app and site; retain system sans for readable
  prose in both.
- Follow each provider's current published asset rules by context. ChatGPT's
  official mark is used beside its named service. Keep exact names visible and
  never imply a category glyph is a provider's logo; no Outlook product mark is
  bundled without the required Microsoft license.
- Keep a selected assistant's background across the entire row, including its
  single overflow target, and expose selection on the assistant button with
  `aria-current`. Keep assistant names to one line, use an ellipsis for long
  names, and preserve the full name in an accessible title. The existing
  responsive browser regression verifies one-line truncation and that the
  selected treatment reaches through the overflow control.
- Community retrieval was manual and individual. No Figma assets were copied,
  no provider was contacted, and no live service was used. Individual frames
  were inspected; no provider artwork was copied from the Figma file.
