/* Composer family — shared writing behavior for every request surface.
   Owned here so chat, first-run, setup, task briefs and inline answers cannot
   drift apart on autogrow, IME safety, Enter semantics or the limit counter.

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

  /* Auto-grow is mounted on every writing surface except the chat composer
     (#composer-box), which mounts its own alongside its draft persistence.
     Idempotent through data-hutch-autogrow: the sweep at DOMContentLoaded
     covers markup that already exists, the observer covers surfaces the SPA
     renders later (first-run, inline answers, phone forms). */
  function mountSurfaceAutogrow() {
    document.querySelectorAll("textarea.hutch-composer__textarea").forEach((textarea) => {
      mountLimitCounter(textarea);
      if (textarea.dataset.hutchAutogrow || textarea.closest("#composer-box")) return;
      textarea.dataset.hutchAutogrow = "1";
      mountAutogrow(textarea);
    });
  }

  /* Limit counter: Hutch enforces character caps with the maxlength attribute,
     so a draft can never go over — the muted counter appears as the cap is
     approached, its "over" state exists for surfaces that raise the cap after
     the fact, and the shell is never recoloured either way. Mounted only where
     the surface already carries a meta row, so nothing is injected into a
     question card that has no composer footer of its own. */
  function mountLimitCounter(textarea) {
    const limit = parseInt(textarea.getAttribute("maxlength"), 10);
    if (!limit || limit <= 0) return;
    const shell = textarea.closest(".hutch-composer");
    const foot = shell && shell.parentElement && shell.parentElement.querySelector(":scope > .hutch-composer__foot");
    const meta = foot && foot.querySelector(".hutch-composer__meta");
    if (!meta || meta.querySelector(".hutch-composer__counter")) return;
    const counter = document.createElement("span");
    counter.className = "hutch-composer__counter";
    counter.hidden = true;
    meta.appendChild(counter);
    const paint = () => {
      const used = textarea.value.length;
      const nearLimit = used >= Math.ceil(limit * 0.9);
      counter.hidden = !nearLimit;
      if (!nearLimit) return;
      counter.dataset.state = used >= limit ? "over" : "near";
      counter.textContent = used.toLocaleString() + " / " + limit.toLocaleString();
    };
    textarea.addEventListener("input", paint);
    paint();
  }
  document.addEventListener("DOMContentLoaded", mountSurfaceAutogrow);
  if (document.body) new MutationObserver(mountSurfaceAutogrow).observe(document.body, { childList: true, subtree: true });
})();
