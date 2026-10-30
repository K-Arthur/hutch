/* Visual-viewport publisher for responsive layouts.
 *
 * Mobile browsers can shrink the visual viewport (on-screen keyboard) or change
 * it as browser chrome collapses without resizing the layout viewport. This
 * publishes custom properties on the document root so CSS can follow it:
 *   --vvh             current visual viewport height, in px
 *   --keyboard-inset  how much of the layout viewport the keyboard covers, in px
 *   --topbar-h        measured height of a wrapping server-page topbar, in px
 *
 * The SPA frame uses --vvh so the composer stays above the keyboard. No layout
 * is applied here; this file only publishes measurements and degrades to a
 * no-op where the Visual Viewport API is absent.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var viewport = window.visualViewport;
  if (!viewport) return;

  function publish() {
    var height = viewport.height;
    var layoutHeight = window.innerHeight;
    var keyboard = Math.max(0, layoutHeight - height - viewport.offsetTop);
    root.style.setProperty("--vvh", height.toFixed(2) + "px");
    root.style.setProperty("--keyboard-inset", keyboard.toFixed(2) + "px");
  }

  function publishTopbar() {
    var topbar = document.querySelector(".topbar");
    if (topbar) {
      root.style.setProperty("--topbar-h", topbar.offsetHeight.toFixed(2) + "px");
    }
  }

  if (viewport) {
    viewport.addEventListener("resize", publish);
    viewport.addEventListener("scroll", publish);
    publish();
  }
  window.addEventListener("resize", publishTopbar);
  var topbar = document.querySelector(".topbar");
  if (topbar && window.ResizeObserver) {
    new ResizeObserver(publishTopbar).observe(topbar);
  }
  publishTopbar();
})();
