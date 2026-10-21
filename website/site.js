/* hutch marketing site — enhancement layer only.
   The page is fully readable and navigable without this file; it adds
   reveals, the mobile drawer, tabs and (on
   capable pointers) the look-at-cursor frame sequence.
   Motion policy is automatic: prefers-reduced-motion is the control. */
(function () {
  "use strict";
  var root = document.documentElement;
  var reduceMQ = window.matchMedia("(prefers-reduced-motion: reduce)");
  root.classList.add("js");

  /* ------------------------------------------------------ scroll reveals */
  /* Hidden start-states exist only under html.js + no-preference (CSS).
     A watchdog guarantees nothing can strand content: any element still
     hidden after load+2.5s or on pageshow is forced visible. */
  var revealTargets = Array.prototype.slice.call(document.querySelectorAll(
    "#proof .proof-figure, .step-card, .feature, .arch, " +
    ".control-grid, .case, .get-grid, .cta-grid"
  )).filter(function (el) {
    /* A descendant of a closed disclosure has no rendered transition state.
       Revealing it while hidden can leave it transparent when the panel opens. */
    return !el.closest("details:not([open])");
  });
  var io = null;
  if ("IntersectionObserver" in window) {
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
    revealTargets.forEach(function (el) { el.classList.add("reveal"); io.observe(el); });
  }
  function forceVisible(el) { el.classList.add("in"); }
  function revealInView() {
    revealTargets.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < window.innerHeight && r.bottom > 0) forceVisible(el);
    });
  }
  setTimeout(revealInView, 400);                 /* elements already on screen */
  setTimeout(function () { revealTargets.forEach(forceVisible); }, 3000); /* failsafe */
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) revealTargets.forEach(forceVisible);               /* bfcache */
  });

  /* --------------------------------------------------------- mobile drawer */
  var menuBtn = document.getElementById("menu-btn");
  var drawer = document.getElementById("menu-drawer");
  if (menuBtn && drawer && typeof drawer.showModal === "function") {
    menuBtn.addEventListener("click", function () {
      drawer.showModal();
      menuBtn.setAttribute("aria-expanded", "true");
    });
    var closeDrawer = function () {
      if (drawer.open) drawer.close();          /* native close restores focus */
    };
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    drawer.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", closeDrawer); });
    drawer.addEventListener("click", function (e) { if (e.target === drawer) closeDrawer(); });
    drawer.addEventListener("close", function () { menuBtn.setAttribute("aria-expanded", "false"); });
    window.addEventListener("resize", function () { if (window.innerWidth > 1000) closeDrawer(); });
  }

  /* ------------------------------------------------------------ tab groups */
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
      tab.addEventListener("keydown", function (e) {
        var dir = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (e.key === "Home") dir = -i;
        if (e.key === "End") dir = tabs.length - 1 - i;
        if (!dir) return;
        e.preventDefault();
        select(tabs[(i + dir + tabs.length) % tabs.length]);
      });
    });
  });

  /* ------------------------------------- pointer-reactive agent (capable) */
  var subject = document.getElementById("agent");
  var agentImg = subject && subject.querySelector(".weave-agent");
  var capable = "matchMedia" in window && window.matchMedia("(pointer: fine)").matches;
  var canLook = capable && !reduceMQ.matches
    && !(navigator.connection && navigator.connection.saveData)
    && (navigator.hardwareConcurrency || 4) >= 4
    && agentImg;
  if (canLook) {
    var COLS = parseInt(subject.getAttribute("data-cols") || "7", 10);
    var ROWS = parseInt(subject.getAttribute("data-rows") || "3", 10);
    var base = subject.getAttribute("data-frames") || "assets/agent/f";
    var CENTER_C = (COLS - 1) / 2, CENTER_R = (ROWS - 1) / 2;
    var loaded = {}, failed = false, current = "", hasPointerTarget = false;
    var target = { c: CENTER_C, r: CENTER_R };

    function srcFor(c, r) { return base + c + "-p" + r + ".webp"; }
    function preload(c, r) {
      var k = c + "-" + r;
      if (loaded[k] || failed) return;
      var im = new Image();
      im.onload = function () {
        loaded[k] = true;
        if (hasPointerTarget && target.c === c && target.r === r) show(c, r);
      };
      im.onerror = function () { failed = true; };   /* missing set: keep static frame */
      im.src = srcFor(c, r);
    }
    preload(CENTER_C, CENTER_R);

    function show(c, r) {
      if (failed) return;
      var k = c + "-" + r;
      if (!loaded[k] || k === current) return;
      current = k;
      agentImg.src = srcFor(c, r);
    }
    function setStatic() { show(CENTER_C, CENTER_R); }

    var pending = false;
    function tick() {
      pending = false;
      show(target.c, target.r);
    }
    function onMove(e) {
      if (failed) return;
      var rect = subject.getBoundingClientRect();
      /* normalized position of the pointer relative to the agent, widened
         a little so the full range is reachable near the hero */
      var nx = (e.clientX - (rect.left + rect.width / 2)) / (rect.width * 2.2);
      var ny = (e.clientY - (rect.top + rect.height / 2)) / (rect.height * 2.6);
      nx = Math.max(-0.5, Math.min(0.5, nx));
      ny = Math.max(-0.5, Math.min(0.5, ny));
      target.c = Math.round(CENTER_C + nx * (COLS - 1));
      target.r = Math.round(CENTER_R + ny * (ROWS - 1));
      hasPointerTarget = true;
      preload(target.c, target.r);
      if (!pending) { pending = true; requestAnimationFrame(tick); }
    }
    document.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", setStatic, { passive: true });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) document.removeEventListener("pointermove", onMove);
      else document.addEventListener("pointermove", onMove, { passive: true });
    });
  }
})();
