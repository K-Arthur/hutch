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

I found official marks for ChatGPT, Outlook, Gmail, and Google Calendar.
Finding an asset is not the same as having rights to bundle it in Hutch or its
marketing site. Google's current product-icon guidance routes business use
through its Partner Marketing Hub and permission process; Microsoft says
product icons require an express license; and OpenAI's rules require exact
approved artwork and restrict use without permission or outside its terms.
Hutch has no recorded approval or license for these marks, so the app and site
use original Hutch-colored category glyphs instead: calendar, mail, inbox,
sparkle, cloud, and monitor. Exact provider names remain visible beside the
glyphs in Apps & AI. The AI category does not imitate OpenAI's Blossom.
References: [Google product-icon guidance](https://partnermarketinghub.withgoogle.com/brands/google/branding-guidelines/how-to-show-googles-brand/),
[Microsoft Trademark and Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks) and [Microsoft Copyright Permissions](https://www.microsoft.com/en-us/legal/intellectualproperty/copyright/permissions),
and [OpenAI Brand Guidelines](https://openai.com/brand/). The earlier Google
SVG files were from an older icon generation and have been removed; the icon
refresh is documented by [Google Workspace Updates](https://workspaceupdates.googleblog.com/2026/05/introducing-fresh-visual-identity-for-Google-Workspace-app-icons.html).

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
users. The native Mobbin connector is unavailable on the current account's plan,
and the connected Figma preview returned its plan retrieval limit, so no
individual Mobbin screens or additional Figma nodes were independently inspected
for this pass. The two user-supplied images remain the specific evidence used.

## Decisions and validation limits

- Keep the app's system-sans type family and marketing's locally bundled Archivo
  display family as separate, coordinated roles.
- Use original Hutch category glyphs until provider artwork has documented
  permission for both app and marketing use. Keep exact provider names visible;
  never imply a category glyph is the provider's logo.
- Keep a selected assistant's background across the entire row, including its
  single overflow target, and expose selection on the assistant button with
  `aria-current`. Keep assistant names to one line, use an ellipsis for long
  names, and preserve the full name in an accessible title.
- Community retrieval was manual and individual. No Figma assets were copied,
  no provider was contacted, and no live service was used. The connected Figma
  design-preview tool was unavailable for further node extraction at this
  account's current plan limit.
