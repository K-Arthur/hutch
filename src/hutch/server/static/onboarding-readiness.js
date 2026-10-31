/* Onboarding readiness client enhancement (slice 03) */
"use strict";

(function () {
  let lastAnnouncedState = "";

  function announceStateChange() {
    const panel = document.querySelector(".onboarding-readiness-panel");
    if (!panel) return;
    const currentState = panel.getAttribute("data-readiness-state");
    if (currentState && currentState !== lastAnnouncedState) {
      lastAnnouncedState = currentState;
      const badge = panel.querySelector(".readiness-badge");
      if (badge) {
        badge.setAttribute("role", "status");
        badge.setAttribute("aria-live", "polite");
      }
    }
  }

  // Handle network offline / online events
  window.addEventListener("offline", () => {
    let banner = document.getElementById("net-offline-banner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "net-offline-banner";
      banner.className = "onboarding-banner onboarding-banner-warning";
      banner.innerHTML = "<p class='onboarding-banner-title'>Browser is offline</p><p>Network connection lost. Local model routes remain usable offline.</p>";
      const container = document.querySelector(".onboarding");
      if (container) container.prepend(banner);
    }
  });

  window.addEventListener("online", () => {
    const banner = document.getElementById("net-offline-banner");
    if (banner) banner.remove();
  });

  document.addEventListener("DOMContentLoaded", announceStateChange);
  document.addEventListener("htmx:afterSwap", announceStateChange);
})();
