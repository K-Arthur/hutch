// Check and cancel actions for the media jobs list on the Providers page.
// The list is rendered by the server; this adds the buttons, sends the owner-only job calls from this
// same-origin page (the server refuses cross-site writes), then re-fetches the page and swaps the list, so
// the wording of every state stays in one place (the server). Cancel needs a second click, because a
// provider cannot take it back.
(function () {
  "use strict";
  var region = document.getElementById("media-jobs");
  if (!region || !window.fetch || !window.DOMParser) return;

  var pending = null;   // the cancel button waiting for its confirming click

  function listUrl() {
    return "/providers?jobs=" + (region.getAttribute("data-finished") === "1" ? "all" : "open");
  }

  function reveal() {
    Array.prototype.forEach.call(region.querySelectorAll("[hidden][data-job-action], #media-jobs-refresh"),
      function (node) { node.hidden = false; });
  }

  function swap() {
    return fetch(listUrl(), { credentials: "same-origin", headers: { "Accept": "text/html" } })
      .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return response.text(); })
      .then(function (html) {
        var fresh = new DOMParser().parseFromString(html, "text/html").getElementById("media-jobs");
        if (!fresh) return;
        region.replaceChildren.apply(region, Array.prototype.slice.call(fresh.childNodes));
        reveal();
      });
  }

  function say(text) {
    var line = region.querySelector(".media-jobs-bar .hint");
    if (line) line.textContent = text;
  }

  function act(button) {
    var action = button.getAttribute("data-job-action");
    var job = button.getAttribute("data-job");
    button.disabled = true;
    say(action === "cancel" ? "Asking the provider to cancel..." : "Checking with the provider...");
    fetch("/api/v1/media/jobs/" + encodeURIComponent(job) + "/" + action, {
      method: "POST", credentials: "same-origin", headers: { "Accept": "application/json" },
    })
      .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return swap(); })
      .catch(function () { say("That did not go through. Nothing was changed here; refresh the list to see the real state."); })
      .then(function () { var again = document.getElementById("media-jobs-refresh"); if (again) again.focus(); });
  }

  function confirmFirst(button) {
    if (pending && pending !== button) { pending.textContent = "Cancel job"; }
    if (pending === button) { pending = null; act(button); return; }
    pending = button;
    button.textContent = "Confirm: cancel this job";
    say("Press the button again to cancel. The provider may not confirm, and may still bill.");
  }

  region.addEventListener("click", function (event) {
    var button = event.target.closest("[data-job-action]");
    if (button) { (button.getAttribute("data-job-action") === "cancel" ? confirmFirst : act)(button); return; }
    if (event.target.closest("#media-jobs-refresh")) { say("Refreshing..."); swap().catch(function () { say("The list could not be refreshed."); }); }
  });
  region.addEventListener("focusout", function (event) {
    if (pending && event.target === pending) { pending.textContent = "Cancel job"; pending = null; }
  });
  reveal();
})();
