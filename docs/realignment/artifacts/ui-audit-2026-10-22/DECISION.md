# Decision — does the task need new UI?

**No new surface.** Every finding is a defect or design debt in existing screens that people already
use daily (chat, Needs you, Work history, navigation, settings). The right level is to repair the
shared components and the specific screens, not to add a screen, mode, or setting.

- No feature is added or removed; each change keeps the same controls, hooks and routes.
- Two controls change type because their behaviour was already that of another component:
  immediate on/off settings become switches (APG switch pattern; NN/g toggle guidance), and a
  single-choice filter becomes a radio group drawn as the same segments.
- No new theme or "accessible mode": the fixes apply to everyone (no overlay, no opt-in).

**Review tooling, not shipped:** an isolated fixture server with clearly synthetic `mock/demo`
data (long, RTL, CJK, emoji and one-letter names; long URLs; 220-character prompts; pending
approvals), measurement probes and the design-review instrument live in the session scratchpad.
The only shipped tooling change is the CSP fix to `ui-audit.mjs`, which the repository already
carries.

**Not decided here (flagged in FINDINGS):** approval timing and extension, placement of the
persistent "Always allow" grant, the approval ID in every card, persona controls, the assistant
manager filter type, and filler copy on assistant cards.
