/* hutch marketing site enhancement layer.
   Progressive only: without this file everything is readable and navigable.
   Adds: data-js gate, scroll reveals, mobile drawer and accessible tabs. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.setAttribute("data-js", "");

  /* ------------------------------------------------- effects mode (fx) */
  var STORE_KEY = "hutch-fx";
  var mq = window.matchMedia("(prefers-reduced-motion: reduce)");
  var fx;
  try {
    var stored = localStorage.getItem(STORE_KEY);
    fx = (stored === "full" || stored === "reduced") ? stored : (mq.matches ? "reduced" : "full");
  } catch (e) {
    fx = mq.matches ? "reduced" : "full";
  }
  var fxButtons = document.querySelectorAll(".fx-btn");
  var revealTargets;
  function setFx(mode, persist) {
    fx = mode;
    root.setAttribute("data-fx", mode);
    fxButtons.forEach(function (btn) {
      btn.setAttribute("aria-pressed", String(mode === "reduced"));
      var label = btn.querySelector(".fx-state");
      if (label) label.textContent = mode === "reduced" ? "reduced" : "full";
    });
    if (persist) { try { localStorage.setItem(STORE_KEY, mode); } catch (e) {} }
    if (mode === "reduced" && revealTargets) revealAllNow();
  }
  setFx(fx, false);
  fxButtons.forEach(function (btn) {
    btn.addEventListener("click", function () { setFx(fx === "full" ? "reduced" : "full", true); });
  });
  mq.addEventListener && mq.addEventListener("change", function (e) {
    var hasStored = false;
    try { hasStored = !!localStorage.getItem(STORE_KEY); } catch (err) {}
    if (!hasStored) setFx(e.matches ? "reduced" : "full", false);
  });

  /* ------------------------------------------------------ reveal on scroll */
  revealTargets = document.querySelectorAll(
    ".proof-head, .proof-figure, .ledger-row, .step, .runs-grid, .control-grid, .case, .get-grid, .cta-grid"
  );
  function revealAllNow() {
    revealTargets.forEach(function (el) { el.classList.add("in"); });
  }
  if (fx === "full" && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.14, rootMargin: "0px 0px -8% 0px" });
    revealTargets.forEach(function (el) { el.classList.add("reveal"); io.observe(el); });
    window.addEventListener("pageshow", function () {
      /* back/forward cache and deep links: never leave text hidden */
      revealTargets.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) { el.classList.add("in"); io.unobserve(el); }
      });
    });
    if (location.hash) {
      var target = document.querySelector(location.hash);
      if (target) target.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("in"); });
    }
  } else {
    revealAllNow();
  }

  /* ------------------------------------------------------- mobile drawer */
  var menuBtn = document.getElementById("menu-btn");
  var drawer = document.getElementById("menu-drawer");
  if (menuBtn && drawer && typeof drawer.showModal === "function") {
    menuBtn.addEventListener("click", function () {
      drawer.showModal();
      menuBtn.setAttribute("aria-expanded", "true");
      var firstLink = drawer.querySelector("a[href]");
      if (firstLink) firstLink.focus();
    });
    var closeDrawer = function () {
      if (drawer.open) drawer.close();
      menuBtn.setAttribute("aria-expanded", "false");
      menuBtn.focus();
    };
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    drawer.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", closeDrawer); });
    drawer.addEventListener("click", function (e) { if (e.target === drawer) closeDrawer(); }); /* backdrop tap */
    drawer.addEventListener("cancel", function (e) { e.preventDefault(); closeDrawer(); }); /* Escape */
    drawer.addEventListener("close", function () { menuBtn.setAttribute("aria-expanded", "false"); });
    window.addEventListener("resize", function () { if (window.innerWidth > 900 && drawer.open) drawer.close(); });
  } else if (menuBtn && drawer) {
    menuBtn.style.display = "none"; /* no dialog support: nav links stay in header (wrapped) */
    drawer.remove();
  }

  /* ----------------------------------------------------------- tabs */
  document.querySelectorAll(".term-tabs").forEach(function (tablist) {
    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    var select = function (tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !on;
      });
      if (focus !== false) tab.focus();
    };
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(tab, false); });
      tab.addEventListener("keydown", function (ev) {
        var next = i;
        if (ev.key === "ArrowRight") next = (i + 1) % tabs.length;
        else if (ev.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
        else if (ev.key === "Home") next = 0;
        else if (ev.key === "End") next = tabs.length - 1;
        else return;
        ev.preventDefault();
        select(tabs[next]);
      });
    });
  });

})();
