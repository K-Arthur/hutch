/* Commitment tools in the assistant setup checklist.

   The setup form is generated from BOT_SETUP_TOOLS in app.js. This module adds the
   personal-operations tools after app.js has defined the list, so the owner can
   grant them per assistant; no other frontend state is changed. */
(function () {
  "use strict";

  const extras = [
    ["capture_commitment", "Propose commitments",
      "Suggest promises for you to confirm on Today. The assistant cannot confirm them."],
    ["list_commitments", "Read visible commitments",
      "See personal commitments plus the shared spaces you grant this assistant."],
    ["report_commitment_done", "Report completion",
      "Record a completion with evidence for you to verify. Not treated as verified work."],
  ];

  function register() {
    if (typeof BOT_SETUP_TOOLS === "undefined" || !Array.isArray(BOT_SETUP_TOOLS)) return false;
    const known = new Set(BOT_SETUP_TOOLS.map(row => row[0]));
    extras.forEach(row => { if (!known.has(row[0])) BOT_SETUP_TOOLS.push(row); });
    return true;
  }

  if (!register() && typeof document !== "undefined") {
    document.addEventListener("DOMContentLoaded", register, { once: true });
  }
  window.hutchPersonalTools = { register };
})();
