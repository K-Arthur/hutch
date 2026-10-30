/* Hutch server-page app shell: one drawer strategy at <=900px.
 *
 * Mirrors app.js openWorkspace/closeWorkspace so the sidebar behaves the same
 * in both shells: labelled toggle, scrim, inertness while closed, Tab
 * containment, Escape and focus return. Primary navigation therefore has one
 * interaction model on every page.
 */
(function () {
  "use strict";

  var shell = document.querySelector(".hutch-shell");
  var rail = document.getElementById("workspace");
  var toggle = document.getElementById("nav-toggle");
  if (!shell || !rail || !toggle) return;

  var scrim = document.getElementById("ws-scrim");
  var close = document.getElementById("ws-close");
  var narrow = window.matchMedia("(max-width: 900px)");

  function syncInert() {
    rail.inert = narrow.matches && !rail.classList.contains("open");
  }

  function openDrawer() {
    rail.classList.add("open");
    shell.classList.add("nav-open");
    syncInert();
    if (scrim) scrim.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", "Close menu");
    if (close) close.hidden = false;
    if (window.HutchOverlay && window.HutchOverlay.lockScroll) window.HutchOverlay.lockScroll();
    var first = rail.querySelector("a, button:not([hidden]), summary");
    if (first) first.focus();
  }

  function closeDrawer(restoreFocus) {
    if (!rail.classList.contains("open")) return;
    rail.classList.remove("open");
    shell.classList.remove("nav-open");
    syncInert();
    if (scrim) scrim.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open menu");
    if (close) close.hidden = true;
    if (window.HutchOverlay && window.HutchOverlay.unlockScroll) window.HutchOverlay.unlockScroll();
    if (restoreFocus) toggle.focus();
  }

  toggle.addEventListener("click", function () {
    if (rail.classList.contains("open")) closeDrawer();
    else openDrawer();
  });
  if (close) close.addEventListener("click", function () { closeDrawer(true); });
  if (scrim) scrim.addEventListener("click", function () { closeDrawer(true); });

  document.addEventListener("keydown", function (ev) {
    if (!rail.classList.contains("open")) return;
    if (ev.key === "Escape") { ev.preventDefault(); closeDrawer(true); return; }
    if (ev.key !== "Tab") return;
    var focusable = Array.prototype.slice
      .call(rail.querySelectorAll("a, button:not([hidden]), summary"))
      .filter(function (el) { return el.getClientRects().length; });
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    if (ev.shiftKey && document.activeElement === first) {
      ev.preventDefault(); last.focus();
    } else if (!ev.shiftKey && document.activeElement === last) {
      ev.preventDefault(); first.focus();
    }
  });

  var onBreakpointChange = function () { closeDrawer(); syncInert(); };
  if (narrow.addEventListener) narrow.addEventListener("change", onBreakpointChange);
  else if (narrow.addListener) narrow.addListener(onBreakpointChange);

  syncInert();
})();
