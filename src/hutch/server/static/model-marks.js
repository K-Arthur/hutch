/* Vendor marks and the where-it-runs icon for model routes.
   Brand artwork is bundled locally (static/brands, provenance in docs/brand-assets.md);
   nothing is fetched. Anything without artwork gets a monogram of its model family on a
   tile whose hue comes from that family. Colour is identity only, never status. */
(function () {
  "use strict";

  const SVG = {
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    chip: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/>',
    cloud: '<path d="M7 18a4 4 0 0 1-.6-7.96A6 6 0 0 1 18 9.5a4.2 4.2 0 0 1-.5 8.5z"/>',
  };
  const ico = (n, size = 16) =>
    `<svg class="ms-ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SVG[n] || ""}</svg>`;
  const escHtml = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const BRAND_FILES = { openai: "openai-white-monoblossom.svg", anthropic: "anthropic-symbol-ivory.svg" };
  // The route names its maker: a provider or connection such as openai, chatgpt,
  // anthropic or claude, or the vendor segment of connection/vendor/model. A local
  // runtime never carries a maker's artwork, whatever the model is called.
  const brandOfMaker = maker => /^(openai|chatgpt)/.test(maker) ? "openai" : /^(anthropic|claude)/.test(maker) ? "anthropic" : "";
  const LOCAL_RUNTIMES = new Set(["ollama", "llamacpp", "llama.cpp", "lmstudio", "vllm"]);
  const hash = text => [...String(text)].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

  function markOf(spec) {
    const parts = String(spec).split("/");
    const model = (parts.length >= 3 ? parts.slice(2).join("/") : parts.slice(1).join("/")).toLowerCase();
    const family = (model.match(/^[a-z]+/) || [""])[0];
    const maker = (parts.length >= 3 ? parts[1] : parts[0]).toLowerCase();          // openrouter/anthropic/x, opencode/openai/x
    const local = LOCAL_RUNTIMES.has(parts[0].toLowerCase());
    const brand = local ? "" : brandOfMaker(maker);
    const name = family || maker || "?";
    return { brand, letter: name[0].toUpperCase(), hue: hash(name) % 360, local };
  }

  // hosted: true/false when the catalog says, otherwise inferred from the runtime in the route.
  function html(spec, hosted) {
    const mark = markOf(spec);
    const away = hosted == null ? !mark.local : hosted;
    return `<span class="ms-mark${mark.brand ? " has-brand" : ""}" style="--mk-h:${mark.hue}" aria-hidden="true">` +
      (mark.brand ? `<img src="/static/brands/${BRAND_FILES[mark.brand]}" alt="" width="60%" height="60%" decoding="async">`
                  : `<span class="ms-mark-letter" data-letter="${escHtml(mark.letter)}"></span>`) +
      `<span class="ms-mark-where ${away ? "is-hosted" : "is-local"}">${ico(away ? "cloud" : "chip", 10)}</span></span>`;
  }

  window.hutchModelMarks = { ico, html };
})();
