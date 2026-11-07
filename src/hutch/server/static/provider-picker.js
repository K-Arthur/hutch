// Live refresh for the route picker on a provider page.
// The form is a plain GET that the server renders; this only fetches that same page and swaps the result
// element, so the labels and honesty rules stay in one place (the server) and nothing is composed here.
(function () {
  "use strict";
  var form = document.getElementById("route-picker-form");
  var result = document.getElementById("route-picker-result");
  if (!form || !result || !window.fetch || !window.DOMParser) return;

  var timer = null;
  var latest = 0;

  function url() {
    var params = new URLSearchParams(new FormData(form));
    return form.getAttribute("action").split("#")[0] + "?" + params.toString();
  }

  function refresh() {
    var ticket = ++latest;
    fetch(url(), { credentials: "same-origin", headers: { "Accept": "text/html" } })
      .then(function (response) { if (!response.ok) throw new Error(String(response.status)); return response.text(); })
      .then(function (html) {
        if (ticket !== latest) return;   // a newer keystroke already asked again
        var fresh = new DOMParser().parseFromString(html, "text/html").getElementById("route-picker-result");
        if (fresh) result.replaceChildren.apply(result, Array.prototype.slice.call(fresh.childNodes));
      })
      .catch(function () {
        var note = document.createElement("p");
        note.className = "hint";
        note.textContent = "The route could not be checked just now. Use Resolve route to try again.";
        result.replaceChildren(note);
      });
  }

  function later() { clearTimeout(timer); timer = setTimeout(refresh, 300); }

  form.addEventListener("submit", function (event) { event.preventDefault(); clearTimeout(timer); refresh(); });
  form.addEventListener("input", later);
  form.addEventListener("change", later);
})();
