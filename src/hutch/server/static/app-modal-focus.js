/* Focus return for the legacy openModal call sites.

   Moved out of app.js to keep the frozen dashboard bundle under its line cap.
   The modal primitive returns focus to the exact trigger; this resolver runs
   first for the historical cases where a live SSE refresh replaced that trigger
   and an equivalent control is the better landing point. Returns true when it
   has handled the focus move so the primitive does not move focus again. */
(function () {
  "use strict";
  function q(sel, el) { return (el || document).querySelector(sel); }
  function qa(sel, el) { return [...(el || document).querySelectorAll(sel)]; }
  window.hutchModalFocus = function (modalReturnFocus, FACT_BUTTONS) {
    FACT_BUTTONS = FACT_BUTTONS || [];
    if (modalReturnFocus?.dataset.receiptReview) {
      const target = qa("[data-receipt-review]").find(b => b.dataset.receiptReview === modalReturnFocus.dataset.receiptReview);
      (target || q("#chat-prompt") || q("#needs-you-open"))?.focus();
    } else if (FACT_BUTTONS.some(([field]) => modalReturnFocus?.dataset[field])) {
      const [field, selector] = FACT_BUTTONS.find(([field]) => modalReturnFocus.dataset[field]);
      (qa(selector).find(button => button.dataset[field] === modalReturnFocus.dataset[field]) || q("#chat-prompt"))?.focus();
    } else if (modalReturnFocus?.dataset.notionAccess) {
      (qa("[data-notion-access]").find(button => button.dataset.notionAccess === modalReturnFocus.dataset.notionAccess) || q("#notion-connect") || q("#nav-toggle"))?.focus();
    } else if (modalReturnFocus?.dataset.backgroundProvider) {
      (qa("[data-background-provider]").find(button =>
        button.dataset.backgroundProvider === modalReturnFocus.dataset.backgroundProvider) || q("#nav-toggle"))?.focus();
    } else if (modalReturnFocus?.dataset.workflowAction && modalReturnFocus?.dataset.workflowId) {
      (qa("[data-workflow-action]").find(button =>
        button.dataset.workflowAction === modalReturnFocus.dataset.workflowAction &&
        button.dataset.workflowId === modalReturnFocus.dataset.workflowId) || q("#chat-prompt"))?.focus();
    } else if (modalReturnFocus?.dataset.workflowSuggestionRun) {
      (qa("[data-workflow-suggestion-run]").find(button =>
        button.dataset.workflowSuggestionRun === modalReturnFocus.dataset.workflowSuggestionRun) || q("#chat-prompt"))?.focus();
    } else if (modalReturnFocus?.dataset.channelToggle) {
      (qa("[data-channel-toggle]").find(button => button.dataset.channelToggle === modalReturnFocus.dataset.channelToggle) || q("#nav-toggle"))?.focus();
    } else if (modalReturnFocus?.dataset.channelReconcile) {
      const channelId = modalReturnFocus.closest("[data-channel]")?.dataset.channel;
      (qa("[data-channel-deliveries]").find(button =>
        button.dataset.channelDeliveries === channelId) || q("#nav-toggle"))?.focus();
    } else if (modalReturnFocus?.isConnected && modalReturnFocus.getClientRects().length) {
      modalReturnFocus.focus();
    } else {
      (q("#chat-prompt") || q("#nav-toggle"))?.focus();
    }
    return true;
  };
})();
