# Connections setup UX review — 2026-10-10

This review focused on configuring Google Calendar and the Gmail private preview from Hutch's
Connections page. It is a design-pattern review, not evidence about user prevalence or provider
eligibility.

## Individual reference screens inspected

- [Bobo Messenger dark Settings](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-33): a distinct account header followed by a short, grouped list of settings. The pattern supports one clear entry point and keeps secondary settings out of the main chat surface.
- [Bobo Messenger dark Security](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-31): each security choice has a direct label and control; deeper changes are separate actions.
- [Bobo Messenger dark chat list](https://www.figma.com/design/9HXDgkK25xdCOI5ifRXEY3/Bobo---Chatbot-Messenger-App-UI-Kit--Preview-?node-id=1627-58): active and ended chats use clear sections, with repeated rows kept visually consistent.

These are mobile screens from the Figma Community Bobo chatbot messenger kit. Their structure was
inspected individually; Hutch uses its own main-branch design tokens, typography, colors, and
mascots. No Figma assets were copied.

## Provider constraints checked

Google's current Gmail scope table classifies `gmail.readonly` as restricted. Its restricted-scope
verification guidance says server-side access to restricted data can require an annual security
assessment. For an OAuth app left in Testing, Google's audience guidance limits test users to 100
and says authorizations and refresh tokens expire after seven days. These provider rules explain
why Gmail stays a restricted private preview; they are not claims about how often users encounter
the limits. Sources checked 2026-10-10: [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[restricted-scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification),
and [OAuth audience and testing limits](https://support.google.com/cloud/answer/15549945?hl=en).

## Decision for Hutch

Calendar and Gmail share one public Google Desktop OAuth client ID, but keep separate connection
cards because their requested scopes and data restrictions differ. The client field lives in one
disclosure inside the Google Calendar section rather than appearing as another top-level sidebar or
navigation destination. It opens by default when setup is missing, explains the minimum Cloud
Console steps, and distinguishes a public client ID from a secret or token. Gmail's test-user,
expiry, and restricted-scope details stay with Gmail's own controls. Setup, unavailable, operator-
managed and client-change confirmation states were checked at desktop, tablet, 390px phone, and
320px compact-phone widths; the smallest action row stacks so labels do not wrap.

When a Google account is already connected, changing the client ID first explains that sign-in or
refresh may need reconnection. Clearing the ID warns that account records and tokens remain. An
operator environment value remains authoritative and read-only in Hutch. Browser tests check these
flows at desktop, tablet, 390px phone, and 320px compact-phone widths, including the confirmation
dialog, touch targets, and horizontal overflow.

## Reference access boundary

Mobbin web and iOS screen searches were attempted for account-connection setup. Both returned an
`INVALID_ARGUMENT` response stating that a paid Mobbin plan is required, so this review does not
claim to have examined Mobbin screens. The Figma Community file above remained accessible and was
used as the reference source for individual mobile settings and chat-list screens.
