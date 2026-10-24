/* Composer family — shared writing behavior for every request surface.
   Owned here so chat, first-run, setup, task briefs and inline answers cannot
   drift apart on autogrow, IME safety, or Enter semantics.

   IME rule (Open WebUI #16608 class): Enter never submits while a composition
   is active. Composition state is recovered from the event itself
   (e.isComposing / keyCode 229), never from a sticky flag, so a missed
   `compositionend` (assistant-ui #3923 class) cannot freeze the field. */
(function () {
  "use strict";

  const DEFAULT_MAX_HEIGHT = 220;

  function isComposing(event) {
    return Boolean(event.isComposing || event.keyCode === 229);
  }

  /* Resize to content up to maxHeight; the value stays in px so long drafts
     scroll instead of pushing the composer out of the viewport. */
  function autogrow(textarea, maxHeight = DEFAULT_MAX_HEIGHT) {
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, maxHeight) + "px";
  }

  function mountAutogrow(textarea, { maxHeight = DEFAULT_MAX_HEIGHT, onInput = null } = {}) {
    const resize = () => autogrow(textarea, maxHeight);
    textarea.addEventListener("input", () => {
      resize();
      if (onInput) onInput();
    });
    resize();
    return { resize };
  }

  /* Enter submits only when the surface's own enterSends() allows it and no
     composition is active; Shift+Enter always inserts a newline. Returns an
     unmount function. */
  function mountEnterSubmit(textarea, { enterSends, submit }) {
    const onKeyDown = event => {
      if (event.key !== "Enter" || event.shiftKey) return;
      if (isComposing(event)) return;   // never submit mid-IME-composition
      if (!enterSends()) return;
      event.preventDefault();
      submit();
    };
    textarea.addEventListener("keydown", onKeyDown);
    return () => textarea.removeEventListener("keydown", onKeyDown);
  }

  window.hutchComposer = { autogrow, mountAutogrow, mountEnterSubmit, isComposing };
})();
