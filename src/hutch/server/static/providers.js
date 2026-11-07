// Progressive filtering for the provider catalogue index.
// Every row is rendered server-side and stays in the DOM; without this script the form stays hidden and
// the full list is shown. Filters combine with AND, search terms combine with AND, and the state lives in
// the query string (?q=&category=&status=&auth=&service=) so a filtered view can be linked and survives reload.
(function () {
  "use strict";
  var form = document.getElementById("provider-filters");
  var rows = Array.prototype.slice.call(document.querySelectorAll("[data-provider-card]"));
  if (!form || !rows.length) return;

  var search = document.getElementById("provider-search");
  var selects = Array.prototype.slice.call(form.querySelectorAll("select[data-filter]"));
  var status = document.getElementById("provider-filter-status");
  var empty = document.getElementById("provider-no-match");
  var sections = Array.prototype.slice.call(document.querySelectorAll("[data-category-section]"));
  var clear = document.getElementById("provider-filter-clear");

  function tokens(value) { return (value || "").split(/\s+/).filter(Boolean); }

  function readState() {
    var state = { q: search.value.trim().toLowerCase() };
    selects.forEach(function (select) { state[select.getAttribute("data-filter")] = select.value; });
    return state;
  }

  function matches(row, state) {
    if (state.category && row.getAttribute("data-category") !== state.category) return false;
    if (state.status && row.getAttribute("data-status") !== state.status) return false;
    if (state.auth && tokens(row.getAttribute("data-auth")).indexOf(state.auth) === -1) return false;
    if (state.service && tokens(row.getAttribute("data-services")).indexOf(state.service) === -1) return false;
    var haystack = row.getAttribute("data-search") || "";
    return tokens(state.q).every(function (term) { return haystack.indexOf(term) !== -1; });
  }

  function describe(state, shown) {
    var active = ["q", "category", "status", "auth", "service"].some(function (key) { return state[key]; });
    var count = shown + " of " + rows.length + " providers";
    if (!shown) return "No provider matches those filters.";
    return active ? "Showing " + count + "." : "Showing all " + rows.length + " providers.";
  }

  function writeQuery(state) {
    var params = new URLSearchParams();
    Object.keys(state).forEach(function (key) { if (state[key]) params.set(key, state[key]); });
    var query = params.toString();
    var target = location.pathname + (query ? "?" + query : "") + location.hash;
    try { history.replaceState(null, "", target); } catch (error) { /* sandboxed frame: the filter still works */ }
  }

  function apply() {
    var state = readState();
    var shown = 0;
    rows.forEach(function (row) {
      var visible = matches(row, state);
      row.hidden = !visible;
      if (visible) shown += 1;
    });
    sections.forEach(function (section) {
      section.hidden = !section.querySelector("[data-provider-card]:not([hidden])");
    });
    if (empty) empty.hidden = shown !== 0;
    status.textContent = describe(state, shown);
    writeQuery(state);
  }

  function restore() {
    var params = new URLSearchParams(location.search);
    search.value = params.get("q") || "";
    selects.forEach(function (select) {
      var wanted = params.get(select.getAttribute("data-filter")) || "";
      select.value = wanted;
      if (select.value !== wanted) select.value = "";   // an unknown value in the URL is ignored, not trusted
    });
  }

  function reset() {
    search.value = "";
    selects.forEach(function (select) { select.value = ""; });
    apply();
    search.focus();
  }

  form.hidden = false;
  if (clear) clear.hidden = false;
  form.addEventListener("submit", function (event) { event.preventDefault(); apply(); });
  search.addEventListener("input", apply);
  search.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && search.value) { search.value = ""; apply(); }
  });
  selects.forEach(function (select) { select.addEventListener("change", apply); });
  if (clear) clear.addEventListener("click", reset);
  restore();
  apply();
})();
