/* Visual-viewport publisher for responsive layouts.
 *
 * Mobile browsers can shrink the visual viewport (on-screen keyboard) or change
 * it as browser chrome collapses without resizing the layout viewport. This
 * publishes two custom properties on the document root so CSS can follow it:
 *   --vvh             current visual viewport height, in px
 *   --keyboard-inset  how much of the layout viewport the keyboard covers, in px
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

  viewport.addEventListener("resize", publish);
  viewport.addEventListener("scroll", publish);
  publish();
})();
