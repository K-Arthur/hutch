"""Page-level measurements used by the responsive validation run.

Each check is one page.evaluate call returning JSON-serialisable data, so the
orchestrator stays orchestration only and every assertion is independently
readable and re-runnable.
"""

from __future__ import annotations

OVERFLOW_JS = r"""() => {
  const vw = window.innerWidth;
  const doc = document.documentElement;
  const body = document.body;
  const offenders = [];
  const seen = new Set();
  for (const el of document.querySelectorAll("body *")) {
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    if (rect.right <= vw + 1) continue;
    const cs = getComputedStyle(el);
    if (cs.position === "fixed") continue;
    if (el.closest("[data-responsive-overflow-ok]")) continue;
    const tag = el.tagName.toLowerCase();
    const id = el.id ? "#" + el.id : "";
    const raw = typeof el.className === "string" ? el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
    const label = tag + id + (raw ? "." + raw : "");
    if (seen.has(label)) continue;
    seen.add(label);
    offenders.push({label: label, right: Math.round(rect.right), width: Math.round(rect.width)});
    if (offenders.length >= 8) break;
  }
  const bodyWidth = body ? body.scrollWidth : doc.scrollWidth;
  return {
    viewport_width: vw,
    document_width: doc.scrollWidth,
    body_width: bodyWidth,
    overflow_px: Math.max(0, Math.max(doc.scrollWidth, bodyWidth) - vw),
    offenders: offenders
  };
}"""

TARGETS_JS = r"""(thresholds) => {
  function describe(el) {
    const tag = el.tagName.toLowerCase();
    const id = el.id ? "#" + el.id : "";
    const raw = typeof el.className === "string" ? el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
    const text = (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 40);
    return tag + id + (raw ? "." + raw : "") + (text ? " [" + text + "]" : "");
  }
  const selector = "button, a[href], input:not([type='hidden']), select, textarea, summary, "
    + "[role='button'], [role='tab'], [role='menuitem'], [role='switch']";
  const under_min = [];
  const under_comfort = [];
  let total = 0;
  for (const el of document.querySelectorAll(selector)) {
    if (el.disabled) continue;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    if (el.closest("[inert]") || el.closest("[aria-hidden='true']")) continue;
    if (el.tagName === "A" && cs.display === "inline") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    total += 1;
    const item = {label: describe(el), width: Math.round(rect.width), height: Math.round(rect.height)};
    if (rect.width < thresholds.min || rect.height < thresholds.min) under_min.push(item);
    if (rect.width < thresholds.comfort || rect.height < thresholds.comfort) under_comfort.push(item);
  }
  return {
    total: total,
    under_min: under_min.slice(0, 12),
    under_min_count: under_min.length,
    under_comfort: under_comfort.slice(0, 12),
    under_comfort_count: under_comfort.length
  };
}"""

CONTRAST_JS = r"""() => {
  function parseColor(value) {
    const match = value.match(/rgba?\(([^)]+)\)/);
    if (!match) return null;
    const parts = match[1].split(",").map(function (part) { return parseFloat(part.trim()); });
    return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
  }
  function blend(top, bottom) {
    const alpha = top.a + bottom.a * (1 - top.a);
    if (alpha <= 0) return {r: 0, g: 0, b: 0, a: 0};
    const channel = function (front, back) {
      return (front * top.a + back * bottom.a * (1 - top.a)) / alpha;
    };
    return {r: channel(top.r, bottom.r), g: channel(top.g, bottom.g),
            b: channel(top.b, bottom.b), a: alpha};
  }
  function effectiveBackground(el) {
    const layers = [];
    let node = el;
    while (node) {
      const color = parseColor(getComputedStyle(node).backgroundColor);
      if (color && color.a > 0) {
        layers.push(color);
        if (color.a >= 0.999) break;
      }
      node = node.parentElement;
    }
    let result = {r: 9, g: 9, b: 11, a: 1};
    for (let index = layers.length - 1; index >= 0; index -= 1) result = blend(layers[index], result);
    return result;
  }
  function luminance(color) {
    const channel = function (value) {
      const scaled = value / 255;
      return scaled <= 0.04045 ? scaled / 12.92 : Math.pow((scaled + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
  }
  function contrastRatio(first, second) {
    const a = luminance(first);
    const b = luminance(second);
    const high = Math.max(a, b);
    const low = Math.min(a, b);
    return (high + 0.05) / (low + 0.05);
  }
  const samples = [];
  const violations = [];
  const elements = document.querySelectorAll("h1, h2, h3, h4, p, li, td, th, button, a, label, span");
  for (const el of elements) {
    if (el.closest("[aria-hidden='true']")) continue;
    const direct = Array.from(el.childNodes).filter(function (node) {
      return node.nodeType === Node.TEXT_NODE;
    }).map(function (node) { return node.textContent; }).join(" ").trim();
    if (direct.length < 2) continue;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    if (parseFloat(cs.opacity) < 0.5) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    const foreground = parseColor(cs.color);
    if (!foreground) continue;
    const background = effectiveBackground(el);
    const text = foreground.a < 1 ? blend(foreground, background) : foreground;
    const ratio = contrastRatio(text, background);
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const required = large ? 3 : 4.5;
    const item = {tag: el.tagName.toLowerCase(), text: direct.slice(0, 48),
                  ratio: Math.round(ratio * 100) / 100, required: required};
    samples.push(item);
    if (ratio + 0.005 < required) violations.push(item);
    if (samples.length >= 400) break;
  }
  return {sampled: samples.length, violations: violations.slice(0, 20),
          violation_count: violations.length};
}"""


VIEWPORT_JS = r"""() => {
  const meta = document.querySelector("meta[name='viewport']");
  const content = meta ? (meta.getAttribute("content") || "") : "";
  return {
    present: !!meta,
    content: content,
    width_device: /width\s*=\s*device-width/i.test(content),
    viewport_fit_cover: /viewport-fit\s*=\s*cover/i.test(content)
  };
}"""


NAV_JS = r"""() => {
  const nav = document.getElementById("primary-nav");
  const toggle = document.getElementById("nav-toggle");
  if (!nav) return {present: false};
  const cs = getComputedStyle(nav);
  const rect = nav.getBoundingClientRect();
  const links = Array.from(nav.querySelectorAll("a")).filter(function (link) {
    const box = link.getBoundingClientRect();
    const style = getComputedStyle(link);
    return box.width > 0 && box.height > 0 && style.display !== "none"
      && style.visibility !== "hidden";
  });
  const toggleStyle = toggle ? getComputedStyle(toggle) : null;
  return {
    present: true,
    nav_visible: rect.width > 0 && rect.height > 0 && cs.visibility !== "hidden"
      && parseFloat(cs.opacity) > 0.5 && cs.pointerEvents !== "none",
    nav_display: cs.display,
    nav_scroll_overflow: Math.max(0, nav.scrollWidth - nav.clientWidth),
    visible_links: links.length,
    total_links: nav.querySelectorAll("a").length,
    toggle_display: toggleStyle ? toggleStyle.display : null,
    toggle_expanded: toggle ? toggle.getAttribute("aria-expanded") : null
  };
}"""


def measure_viewport(page) -> dict:
    """The viewport contract declared by the document head."""
    return page.evaluate(VIEWPORT_JS)


KEYBOARD_JS = r"""() => {
  function box(element) {
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    return {top: Math.round(rect.top), bottom: Math.round(rect.bottom),
            height: Math.round(rect.height)};
  }
  const viewport = window.visualViewport;
  const shell = document.querySelector(".app-shell");
  const composer = document.querySelector(".composer")
    || document.querySelector(".hutch-composer");
  const transcript = document.querySelector(".chat-scroll");
  const focused = document.activeElement;
  return {
    visual_height: Math.round(viewport ? viewport.height : window.innerHeight),
    layout_height: Math.round(window.innerHeight),
    vvh: getComputedStyle(document.documentElement).getPropertyValue("--vvh").trim(),
    keyboard_inset: getComputedStyle(document.documentElement)
      .getPropertyValue("--keyboard-inset").trim(),
    shell: box(shell),
    composer: box(composer),
    transcript: transcript ? {scroll_height: transcript.scrollHeight,
                              client_height: transcript.clientHeight} : null,
    focused: focused ? {tag: focused.tagName.toLowerCase(), box: box(focused)} : null
  };
}"""


def measure_nav(page) -> dict:
    """The server-page navigation model: visible nav, overflow and toggle state."""
    return page.evaluate(NAV_JS)


def measure_keyboard(page) -> dict:
    """Layout geometry after the visual viewport shrinks (keyboard simulation)."""
    return page.evaluate(KEYBOARD_JS)


def measure_overflow(page) -> dict:
    """Horizontal overflow of the document plus the elements extending past it."""
    return page.evaluate(OVERFLOW_JS)


def measure_targets(page, min_px: int, comfort_px: int) -> dict:
    """Interactive-target sizes, split at the WCAG 2.5.8 minimum and the comfort floor."""
    return page.evaluate(TARGETS_JS, {"min": min_px, "comfort": comfort_px})


def measure_contrast(page) -> dict:
    """WCAG contrast of visible text, resolving translucent backgrounds by compositing."""
    return page.evaluate(CONTRAST_JS)
