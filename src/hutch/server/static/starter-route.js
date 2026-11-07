/* The route a new person starts with, and the plain notice that goes with it.

   One decision, shared by first run, the new-assistant setup and the Models page, so they cannot disagree.
   It is a pure function over two reads the browser already makes (OpenCode status and the model route
   list); it saves nothing and starts nothing. Whatever it picks is only *preselected*: a person confirms
   it by creating the assistant, and changes it in Settings or on the assistant's AI model tab.

   Order, most private first:
     1. a ready model on this computer (nothing leaves it);
     2. a provider the person already connected (their own account and terms);
     3. a free OpenCode model, hosted by someone else, so it always carries a notice.
   OpenCode exposes only free models until an account is connected, so an unconnected profile is all free;
   once connected, only models whose id says "free" count as free and a paid model is never a "free" start. */
(() => {
  "use strict";

  const FREE_ID = /(^|[-_.])free($|[-_.])/i;
  const TOOLING = /tool/i;
  const lastSegment = spec => String(spec || "").split("/").filter(Boolean).at(-1) || String(spec || "");

  const readyRoutes = routes => (Array.isArray(routes) ? routes : [])
    .filter(route => route && route.state === "ready" && typeof route.spec === "string" && route.spec);

  function rank(models) {
    // Agents lean on tool calls, then on room to work; ties keep OpenCode's own order.
    return models.map((model, index) => ({ model, index })).sort((a, b) => {
      const tools = Number(TOOLING.test((b.model.capabilities || []).join(" "))) - Number(TOOLING.test((a.model.capabilities || []).join(" ")));
      return tools || (Number(b.model.context) || 0) - (Number(a.model.context) || 0) || a.index - b.index;
    }).map(item => item.model);
  }

  function openCodeChoice(openCode) {
    const models = (Array.isArray(openCode?.models) ? openCode.models : []).filter(model => typeof model?.spec === "string" && model.spec);
    if (!openCode?.ready || !models.length) return null;
    const connected = !!openCode.authenticated;
    const free = models.filter(model => !connected || FREE_ID.test(String(model.model_id || model.spec)));
    const pool = free.length ? free : connected ? models : [];
    if (!pool.length) return null;
    const pick = rank(pool)[0];
    return { kind: "opencode", runtime: "opencode", model: pick.spec, label: pick.name || lastSegment(pick.spec),
             hosted: true, free: free.length > 0, count: models.length, connected };
  }

  function choose(openCode, routes) {
    const ready = readyRoutes(routes);
    const local = ready.find(route => route.hosted === false);
    if (local) return { kind: "route", runtime: "builtin", model: local.spec, label: local.label || lastSegment(local.spec),
                        hosted: false, free: false, group: local.group || "" };
    const own = ready.find(route => route.hosted === true);
    if (own) return { kind: "route", runtime: "builtin", model: own.spec, label: own.label || lastSegment(own.spec),
                      hosted: true, free: false, group: own.group || "" };
    return openCodeChoice(openCode);
  }

  // The one sentence that says what was found. "Ready" reads as saved, so it says what exists and, in the same
  // breath, that nothing is saved yet; first run and the Models page both show it, so they say the same thing.
  const NOT_SAVED = "None is saved as the default for new assistants yet.";

  function availability(choice) {
    if (!choice) return "";
    if (choice.kind !== "opencode") return `${choice.group || "A configured provider"} has a model route you can use. ${NOT_SAVED}`;
    const count = choice.count;
    const account = choice.connected ? "A provider account is connected." : "Its available models can be used without a separate account.";
    return `OpenCode is available with ${count} model option${count === 1 ? "" : "s"}. ${account} ${NOT_SAVED}`;
  }

  const CHANGE = "Change it any time: Settings sets the default for new assistants, and an assistant's AI model tab changes just that assistant.";

  function disclosure(choice) {
    if (!choice || choice.hosted !== true) return null;   // a saved choice or a local model needs no notice
    if (choice.free) return {
      kind: "free",
      title: "Free starter model, hosted by OpenCode",
      body: "Whatever you send it leaves this computer, and free hosted models can keep or learn from it. It is a good way to try Hutch with nothing private. Before you share sensitive messages or files, switch to a model on this computer or to your own provider.",
      change: CHANGE,
    };
    return {
      kind: "account",
      title: "Uses a provider you connected",
      body: "Whatever you send goes to that provider under your account's terms, and usage may cost money.",
      change: CHANGE,
    };
  }

  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  function noticeHtml(choice) {
    const note = disclosure(choice);
    if (!note) return "";
    return `<aside class="route-notice" data-kind="${note.kind}" role="note" aria-label="About this starting model">
      <strong class="route-notice-title">${escapeHtml(note.title)}</strong>
      <p>${escapeHtml(note.body)}</p>
      <p class="hint">${escapeHtml(note.change)}</p>
    </aside>`;
  }

  window.hutchStarterRoute = { choose, disclosure, noticeHtml, availability };
})();
