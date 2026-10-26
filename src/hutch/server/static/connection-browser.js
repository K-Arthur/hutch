/* App discovery and focused account settings. No credentials or grants live here. */
(() => {
  const SECTIONS = Object.freeze({
    "google-calendar": ["connection-google-calendar"],
    "google-drive": ["connection-google-drive"],
    "google-docs": ["connection-google-docs"],
    "google-sheets": ["connection-google-sheets"],
    notion: ["connection-notion"],
    gmail: ["connection-gmail"],
    "outlook-calendar": ["connection-outlook-calendar", "connection-outlook-mail"],
    chatgpt: ["connection-chatgpt"],
    phone: ["connection-phone-devices"],
    models: [],
  });

  function mount(root) {
    if (!root?.isConnected) return;
    const directory = root.querySelector("[data-connection-directory]");
    const manager = root.querySelector("#connection-management");
    const heading = root.querySelector("#connection-detail-heading");
    const detail = root.querySelector("[data-connection-detail]");
    if (!directory || !manager || !heading || !detail) return;
    const params = new URLSearchParams((location.hash.split("?")[1] || ""));
    const requested = params.get("app") === "google-workspace" ? "google-drive" : params.get("app") || "";
    const selected = Object.hasOwn(SECTIONS, requested) ? requested : "";
    const entries = [...directory.querySelectorAll("[data-connection-entry]")];
    const entry = entries.find(node => node.dataset.connectionEntry === selected);
    directory.hidden = !!selected;
    detail.hidden = !selected;
    manager.hidden = !selected;
    manager.open = !!selected;
    manager.classList.toggle("is-focused", !!selected);
    root.dataset.selectedConnection = selected;
    if (entry) {
      // Copy only owned markup/text from the catalog, never provider responses.
      const mark = entry.querySelector(".service-mark")?.cloneNode(true);
      heading.replaceChildren();
      if (mark) heading.append(mark);
      const title = document.createElement("h2");
      title.textContent = entry.dataset.connectionTitle;
      title.tabIndex = -1;
      heading.append(title);
      const state = entry.querySelector(".service-state")?.cloneNode(true);
      if (state) heading.append(state);
      const steps = root.querySelector(".connection-steps");
      root.querySelector("[data-connection-open='phone-pair']").hidden = selected !== "phone";
      if (selected === "models" || selected === "chatgpt") {
        steps.hidden = true;
      } else if (selected === "phone") {
        steps.children[0].textContent = "Pair your phone";
        steps.children[1].textContent = "Manage device access";
        steps.children[2].textContent = "Follow your work";
        root.querySelector("#connection-phone-devices").open = true;
      } else if (entry.dataset.connectionState === "connected") {
        steps.children[0].textContent = "Account connected";
        steps.children[0].classList.add("is-complete");
        const check = document.createElement("span");
        check.className = "connection-step-check";
        check.setAttribute("aria-hidden", "true");
        check.innerHTML = window.icon("check");
        steps.children[0].prepend(check);
        steps.children[1].textContent = "Manage assistant access";
      }
      if (["google-drive", "google-docs", "google-sheets"].includes(selected)) {
        steps.children[1].textContent = "Review an action plan";
        steps.children[2].textContent = "Approve exact changes";
      }
      root.querySelector("#connection-detail-description").textContent = entry.querySelector("p")?.textContent || "";
      root.querySelectorAll(".connection-management-content > *").forEach(node => {
        const appSection = node.id.startsWith("connection-") || node.classList.contains("device-manager");
        node.hidden = selected === "models" ? appSection : !SECTIONS[selected].includes(node.id);
      });
      queueMicrotask(() => { if (title.isConnected) title.focus({ preventScroll: true }); });
      if (selected === "google-calendar" && params.get("developer") === "1") {
        const setup = root.querySelector("#google-oauth-setup");
        if (setup) {
          setup.open = true;
          queueMicrotask(() => root.querySelector("#google-oauth-client-id")?.focus());
        }
      }
    }

    const input = root.querySelector("#connection-search");
    const filters = [...root.querySelectorAll("[data-connection-filter]")];
    let filter = "all";
    function apply() {
      const query = (input?.value || "").normalize("NFKC").toLocaleLowerCase().trim();
      let count = 0;
      entries.forEach(node => {
        const connected = node.dataset.connectionState === "connected";
        const matchesState = filter === "all" || (filter === "connected" ? connected : !connected);
        const matchesText = node.textContent.normalize("NFKC").toLocaleLowerCase().includes(query);
        node.hidden = !matchesState || !matchesText;
        if (!node.hidden) count++;
      });
      root.querySelectorAll(".service-group").forEach(group => {
        group.hidden = ![...group.querySelectorAll("[data-connection-entry]")].some(node => !node.hidden);
      });
      const empty = root.querySelector("#connection-empty");
      empty.hidden = !!count;
      root.querySelector("#connection-results").textContent = `${count} connection${count === 1 ? "" : "s"}`;
      filters.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.connectionFilter === filter)));
    }
    input?.addEventListener("input", apply);
    input?.addEventListener("keydown", event => {
      if (event.key === "Escape" && input.value) { event.preventDefault(); input.value = ""; apply(); }
    });
    filters.forEach(button => button.addEventListener("click", () => { filter = button.dataset.connectionFilter; apply(); }));
    root.querySelector("#connection-clear-filters")?.addEventListener("click", () => {
      filter = "all";
      input.value = "";
      apply();
      input.focus();
    });
    apply();
  }

  window.hutchConnections = Object.freeze({ mount });
})();
