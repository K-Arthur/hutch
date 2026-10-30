/* Activity: one destination with three views (Now, History, Conversations).
   It replaces Overview/Activity, Work history and Conversation history
   (docs/realignment/product-spine.md, decision 1). The old hashes keep working:
   canonicalize() rewrites them in place before the router matches a route. */
(() => {
  "use strict";

  const VIEWS = [
    { key: "now", label: "Now", hash: "#/activity", about: "What is running and what needs you" },
    { key: "history", label: "History", hash: "#/activity/history", about: "Past runs and their results" },
    { key: "conversations", label: "Conversations", hash: "#/activity/conversations",
      about: "Find active, archived and imported conversations" },
  ];

  const LEGACY = [
    [/^#\/overview$/, () => "#/activity"],
    [/^#\/chats$/, () => "#/activity/conversations"],
    [/^#\/runs(\?.*)?$/, match => `#/activity/history${match[1] || ""}`],
  ];

  /* Return the canonical hash; when it differs, rewrite the address bar without
     adding a history entry or firing another hashchange. */
  function canonicalize(hash) {
    for (const [pattern, target] of LEGACY) {
      const match = hash.match(pattern);
      if (!match) continue;
      const next = target(match);
      history.replaceState(null, "", next);
      return next;
    }
    return hash;
  }

  function header(key) {
    const view = VIEWS.find(item => item.key === key) || VIEWS[0];
    return `<div class="ctx-id"><div class="ctx-heading"><h1>Activity</h1><span class="ctx-subtitle">${view.about}</span></div></div>`;
  }

  /* Plain links, not ARIA tabs: each view is its own deep-linkable route. */
  function tabs(key) {
    const links = VIEWS.map(view =>
      `<a href="${view.hash}"${view.key === key ? ' aria-current="page"' : ""}>${view.label}</a>`).join("");
    return `<nav class="activity-tabs" aria-label="Activity views">${links}</nav>`;
  }

  window.hutchActivity = { canonicalize, header, tabs };
})();
