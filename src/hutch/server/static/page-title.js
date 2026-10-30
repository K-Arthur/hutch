/* Page titles: one format, `<View> — Hutch`. A destination's view name is its
   sidebar label, read from the sidebar itself, so a title cannot drift from the
   navigation (docs/realignment/product-spine.md). Server pages use the same
   format in templates/base.html. */
(() => {
  "use strict";

  function navLabel(nav) {
    const row = document.querySelector(`.ws-nav [data-nav="${nav}"], .ws-foot-link[data-nav="${nav}"]`);
    return row ? row.textContent.replace(/\s+/g, " ").trim() : "";
  }

  function pageTitle(view) {
    return !view || view === "Hutch" ? "Hutch" : `${view} — Hutch`;
  }

  window.hutchTitle = { navLabel, pageTitle };
})();
