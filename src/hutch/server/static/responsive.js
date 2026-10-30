/* Visual-viewport publisher for responsive layouts.
 *
 * Mobile browsers can shrink the visual viewport (on-screen keyboard) or change
 * it as browser chrome collapses without resizing the layout viewport. This
 * publishes custom properties on the document root so CSS can follow it:
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

  if (viewport) {
    viewport.addEventListener("resize", publish);
    viewport.addEventListener("scroll", publish);
    publish();
  }
})();

/* Incremental live-update accelerator (optional, post-app.js load).
   It lives in its own self-installing script and is discovered here rather than from
   index.html/app.js because those shared dashboard files are another session's parked
   tree; this existing post-app.js slot is the mergeable hook. If the script is missing
   or blocked, the previous polling/refetch behaviour is unchanged. When the parked tree
   lands, this small loader can move into index.html next to app.js. */
(() => {
  try {
    const script = document.createElement("script");
    script.src = "/static/live-updates.js";
    script.async = false;
    script.onerror = () => {};
    document.head.appendChild(script);
  } catch { /* optimisation only: keep the original live-update path */ }
})();