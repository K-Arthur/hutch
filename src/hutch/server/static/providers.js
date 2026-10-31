// Progressive search and category filtering for the provider catalogue page.
// No data is fetched; every card is already rendered server-side and stays in the DOM.
(function () {
  "use strict";
  var input = document.getElementById("provider-search");
  var status = document.getElementById("provider-filter-status");
  var empty = document.getElementById("provider-no-match");
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-category-filter]"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("[data-provider-card]"));
  var sections = Array.prototype.slice.call(document.querySelectorAll("[data-category-section]"));
  if (!input || !cards.length) return;

  var activeCategory = "all";

  function matchesCategory(card) {
    return activeCategory === "all" || card.getAttribute("data-category") === activeCategory;
  }

  function apply() {
    var query = (input.value || "").trim().toLowerCase();
    var visible = 0;
    cards.forEach(function (card) {
      var haystack = card.getAttribute("data-search") || "";
      var show = matchesCategory(card) && (!query || haystack.indexOf(query) !== -1);
      card.hidden = !show;
      if (show) visible += 1;
    });
    sections.forEach(function (section) {
      var any = section.querySelector("[data-provider-card]:not([hidden])");
      section.hidden = !any;
    });
    if (empty) empty.hidden = visible !== 0;
    if (status) status.textContent = "Showing " + visible + " provider" + (visible === 1 ? "" : "s") + ".";
    buttons.forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-category-filter") === activeCategory));
    });
  }

  input.addEventListener("input", apply);
  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      input.value = "";
      activeCategory = "all";
      apply();
    }
  });
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      activeCategory = button.getAttribute("data-category-filter") || "all";
      apply();
    });
  });
  apply();
})();
