# Fundamental integration coverage

This audit extends P6 of the [production checkpoint](desktop-production-2026-10-26.md).
A template, tool name or connection card is not an executed integration. Priorities reflect
the requested marketing, founder-sales, meeting and document workflows. Public availability
is gated separately from fixture validation.

| Priority | Capability | Current Hutch boundary | Next required completion |
| --- | --- | --- | --- |
| Core | Google Calendar | Native read and approved guest-free creation, per-assistant calendar grants | Register/verify publisher app; live consent/read/create/readback |
| Core | Gmail | Local-only search preview; separately approved sending | Restricted-scope release review; live evaluation |
| Core | Google Drive, Docs, Sheets | PKCE account transport and governed plan writes/readback; now visible in Apps & AI | Publisher registration, desktop file Picker, scoped existing-file browsing/read/search; live tests |
| Core | Microsoft mail/calendar | Native narrow reads and separate approved writes; simplified sign-in | Publisher app and non-Linux secure stores; live tests |
| Core | Notion | Official hosted MCP OAuth, per-assistant search/fetch grants, bounded reads, refresh/revoke and schema checks; fixture/browser validated | Live account validation, other-OS credential stores and separately reviewed writes |
| Core | GitHub | Local code tools exist; no governed repository account connector | App/device sign-in, selected repositories, issue/PR/diff reads and separately approved writes; no implicit push/merge |
| Core | Slack / Telegram | Missing durable inbound/outbound gateway adapters | Account/workspace/channel allowlists, durable delivery, duplicate/replay handling and per-bot routing (P5) |
| Core | Local files / PDF / office / CSV | Existing workspace/document tools and artifacts | End-to-end artifact evaluation; retain workspace and formula-injection boundaries |
| Core | Web research / browser | Existing governed tools and local login handoff | Source-quality/live workflow evaluation; retain explicit human credentials |
| Core | Phone supervision | Passkey API/browser surface; now discoverable with host-side code creation | Physical Android/iOS and private-network validation |
| Next | Linux apps and paired phone data | KDE Connect paired-device connection/battery reads, explicit per-device/per-assistant grants, bounded native IPC and canonical receipts; fixture/UI validated | Physical phone/distribution validation; further adapters need separate scope and acceptance; no SMS/notification access |
| Next | Tasks and knowledge | Native durable work/memory exists; no cross-service task sync | Notion first; assess Todoist/Linear against actual target-user workflows rather than adding duplicate task systems |
| Next | Performance marketing | Local reports/CSV and plan contracts; no live Ads reporting connector | Read-only Google Ads reporting, explicit account selection and budget-independent evaluation |
| Later | Cross-channel chat / contacts / other clouds | Not implied by a Google sign-in | Add only specific useful scopes/transports with their own acceptance evidence |

## Transport decisions and official sources

- [Google Workspace MCP](https://developers.google.com/workspace/guides/configure-mcp-servers)
  and [Calendar MCP](https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server)
  are developer preview and still require OAuth configuration. They are candidates for
  expansion, not a workaround for a missing Hutch registration. Retain tested native
  Calendar tools while evaluating preview stability and the canonical tool boundary.
- [Drive scope guidance](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
  recommends narrow scopes and per-file access. A `drive.file` connection must never
  advertise unrestricted Drive search.
- [Notion hosted MCP](https://developers.notion.com/guides/mcp/get-started-with-mcp)
  uses browser OAuth at `https://mcp.notion.com/mcp`; a normal user should not have to
  create a personal integration and copy a token. Its advertised OAuth metadata supports
  S256 PKCE and client registration. Hutch now implements this public-client flow with controlled provider fixtures; live account validation remains open.
- [KDE Connect](https://github.com/KDE/kdeconnect-kde) and
  [its user guide](https://userbase.kde.org/KDEConnect) supply the published interfaces for the narrow Linux connection/battery-status adapter. Phone supervision and access to phone data are different directions of
  trust. Device pairing alone must not authorize sending messages or copying notifications.

Every account-backed connector must have a complete sign-in, select, execute, receipt/readback,
cancel/error, refresh and revoke path. Native device adapters use existing OS pairing and need explicit Hutch grants, cancellation and revocation without pretending to supply OAuth. External content remains untrusted; OAuth consent
does not confer blanket assistant authority. No accounts have been newly connected,
messages sent, purchases made or cloud registrations borrowed during this audit.
