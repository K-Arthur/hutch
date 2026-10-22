#!/usr/bin/env node
/**
 * ui-audit.mjs — measurement-based UI audit (companion to FRONTEND_PIPELINE_PROMPT.md)
 *
 * Why this exists: vision models are unreliable at spotting fine-grained layout defects
 * (overlap, clipping, text overflow). This script MEASURES the rendered DOM instead and
 * produces evidence (JSON + screenshots) that a model of any skill level can act on.
 *
 * Usage:
 *   npm i -D playwright            # (and optionally: npm i -D axe-core)
 *   node ui-audit.mjs <url> [<url> ...] [--out=ui-audit-out] [--widths=320,375,768,1024,1440]
 *        [--schemes=light,dark] [--stress=none,textspacing,pseudo,rtl] [--no-keyboard]
 *        [--wait=networkidle|load|domcontentloaded] [--timeout=30000] [--max-tabs=150]
 *        [--storage=state.json]      # Playwright storageState for authenticated pages
 *        [--selftest]                # prove the checks can FAIL (runs built-in broken fixture)
 *
 * Checks (per URL x width x scheme x stress mode):
 *   horizontal-overflow   page scrolls sideways; lists the elements poking past the viewport
 *   text-clipped          text cut off by overflow:hidden/clip (incl. ellipsis/line-clamp = info)
 *   text-spill            text escapes its own box (e.g. long word in fixed-width button)
 *   collision             visible text/media/controls overlapping each other (not ancestor/descendant)
 *   occluded-control      an interactive element is covered (click would hit something else)
 *   fixed-layer-overlap   a fixed/sticky layer (header, cookie bar, chat bubble, toast) sits on a control
 *   target-size           pointer target < 24x24 CSS px without the WCAG 2.5.8 spacing exception
 *   image-upscaled / image-distorted / image-broken
 *   small-text            rendered text < 12px; input-zoom-ios: inputs < 16px (iOS zooms on focus)
 *   focus-obscured        (keyboard walk) focused element hidden by sticky/fixed content (WCAG 2.4.11)
 *   focus-invisible       (keyboard walk) no computed-style change when focused (heuristic)
 *   focus-trap            (keyboard walk) Tab cycles among a few elements without reaching the end
 *   cls                   cumulative layout shift during load; console-error; request-failed
 *   axe:*                 axe-core violations if axe-core is installed (covers contrast, names, ARIA)
 *
 * Every finding is a CANDIDATE. Intentional overlaps (badge on avatar, layered cards) exist:
 * a human or model must confirm against the screenshot before acting. Never "fix" by hiding.
 */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  for (const m of ['playwright', '@playwright/test', 'playwright-core']) {
    try { return require(m); } catch { /* try next */ }
  }
  console.error('Playwright not found. Run: npm i -D playwright');
  process.exit(2);
}

// ---------------------------------------------------------------------------
// In-page audit (serialised into the browser). Pure DOM; no dependencies.
// ---------------------------------------------------------------------------
function inPageAudit(opts) {
  const o = Object.assign({ tol: 1, minTarget: 24, maxEls: 5000, maxPairs: 400000 }, opts || {});
  const de = document.documentElement;
  const vw = de.clientWidth, vh = window.innerHeight;
  const out = [];
  const push = (f) => out.push(f);

  const cssPath = (el) => {
    if (!el || el.nodeType !== 1) return '';
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const parts = [];
    let n = el;
    while (n && n.nodeType === 1 && parts.length < 5) {
      let p = n.tagName.toLowerCase();
      if (n.id && document.querySelectorAll('#' + CSS.escape(n.id)).length === 1) { parts.unshift('#' + CSS.escape(n.id)); break; }
      const cls = [...n.classList].filter((c) => !/^(is-|has-|js-)|:|\[|\//.test(c)).slice(0, 2);
      if (cls.length) p += '.' + cls.map((c) => CSS.escape(c)).join('.');
      const par = n.parentElement;
      if (par) {
        const same = [...par.children].filter((c) => c.tagName === n.tagName);
        if (same.length > 1) p += `:nth-of-type(${same.indexOf(n) + 1})`;
      }
      parts.unshift(p);
      n = n.parentElement;
    }
    return parts.join(' > ');
  };
  const label = (el) => {
    const t = (el.getAttribute('aria-label') || el.innerText || el.value || el.alt || el.title || '').trim().replace(/\s+/g, ' ');
    return t.slice(0, 60);
  };
  const R = (r) => ({ x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) });
  const inter = (a, b) => {
    const l = Math.max(a.left, b.left), t = Math.max(a.top, b.top);
    const r = Math.min(a.right, b.right), btm = Math.min(a.bottom, b.bottom);
    return r > l && btm > t ? { left: l, top: t, right: r, bottom: btm, width: r - l, height: btm - t } : null;
  };
  const isVisible = (el) => {
    if (el.checkVisibility && !el.checkVisibility({ opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true })) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  // Visible rect after clipping by overflow ancestors (cached per ancestor).
  const clipCache = new Map();
  const clipOf = (anc) => {
    if (clipCache.has(anc)) return clipCache.get(anc);
    const cs = getComputedStyle(anc);
    const clips = cs.overflowX !== 'visible' || cs.overflowY !== 'visible' || cs.clipPath !== 'none' || cs.contain.includes('paint');
    const v = clips ? anc.getBoundingClientRect() : null;
    clipCache.set(anc, v);
    return v;
  };
  // includeSelf: for an element's own text/content rects, the element's own overflow clip applies too
  const visibleRect = (el, r, includeSelf) => {
    let rect = r || el.getBoundingClientRect();
    rect = { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
    let a = includeSelf ? el : el.parentElement;
    while (a && a !== de) {
      const pos = getComputedStyle(a).position;
      const c = clipOf(a);
      if (c) { const i = inter(rect, c); if (!i) return null; rect = i; }
      if (pos === 'fixed') break;
      a = a.parentElement;
    }
    return { ...rect, width: rect.right - rect.left, height: rect.bottom - rect.top };
  };
  const ownTextRects = (el) => {
    const rects = [];
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim()) {
        const rg = document.createRange(); rg.selectNodeContents(n);
        for (const r of rg.getClientRects()) if (r.width > 1 && r.height > 1) rects.push(r);
      }
    }
    return rects;
  };
  const INTERACTIVE = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=radio],[role=switch],[role=tab],[role=menuitem],[role=option],[tabindex]:not([tabindex="-1"]),[contenteditable=""],[contenteditable=true]';
  const all = [...document.body.querySelectorAll('*')].slice(0, o.maxEls).filter(isVisible);
  const interactive = all.filter((e) => e.matches(INTERACTIVE));

  // Fixed/sticky layers (header, cookie bar, chat launcher, toasts, bottom nav)
  const layers = all.filter((e) => { const p = getComputedStyle(e).position; return p === 'fixed' || p === 'sticky'; })
    .filter((e) => !all.some((x) => x !== e && x.contains(e) && ['fixed', 'sticky'].includes(getComputedStyle(x).position)));

  // 1. Horizontal overflow ------------------------------------------------
  if (de.scrollWidth > vw + o.tol) {
    const offenders = all.filter((e) => {
      const r = e.getBoundingClientRect();
      if (!(r.right > vw + o.tol || r.left < -o.tol)) return false;
      return visibleRect(e) && !!(() => { const v = visibleRect(e); return v && (v.right > vw + o.tol || v.left < -o.tol); })();
    });
    const top = offenders.filter((e) => !offenders.some((p) => p !== e && p.contains(e))).slice(0, 15);
    push({ check: 'horizontal-overflow', severity: 'high', msg: `Page scrolls horizontally: scrollWidth ${de.scrollWidth}px > viewport ${vw}px`,
      items: top.map((e) => ({ sel: cssPath(e), rect: R(e.getBoundingClientRect()) })) });
  }

  // 2/3. Clipped text & spilling text -------------------------------------
  for (const e of all) {
    const tr = ownTextRects(e);
    if (!tr.length) continue;
    const cs = getComputedStyle(e);
    const clipsX = ['hidden', 'clip'].includes(cs.overflowX), clipsY = ['hidden', 'clip'].includes(cs.overflowY);
    const ox = e.scrollWidth - e.clientWidth, oy = e.scrollHeight - e.clientHeight;
    if ((clipsX && ox > o.tol + 1) || (clipsY && oy > o.tol + 2)) {
      const intentional = cs.textOverflow === 'ellipsis' || cs.webkitLineClamp !== 'none' && cs.webkitLineClamp !== '';
      push({ check: 'text-clipped', severity: intentional ? 'info' : 'high',
        msg: intentional ? 'Text truncated (ellipsis/line-clamp) — ensure full text is reachable (tooltip, expand, title)' : 'Text cut off by overflow clipping',
        sel: cssPath(e), text: label(e), hiddenPx: { x: Math.max(0, ox), y: Math.max(0, oy) }, rect: R(e.getBoundingClientRect()) });
      continue;
    }
    if (!clipsX && !clipsY && !['inline', 'contents'].includes(cs.display)) {
      const box = e.getBoundingClientRect();
      const spill = tr.some((r) => { const v = visibleRect(e, r); return v && (v.right > box.right + 2 || v.left < box.left - 2); });
      if (spill) push({ check: 'text-spill', severity: 'medium', msg: 'Text extends outside its own box (long word / fixed width / nowrap)', sel: cssPath(e), text: label(e), rect: R(box) });
    }
  }

  // 4. Collisions between visible leaf content -----------------------------
  const MEDIA = 'img,svg,video,canvas,input,select,textarea,button,iframe,[role=img]';
  const boxes = [];
  for (const e of all) {
    if (e.closest('svg') && e.tagName.toLowerCase() !== 'svg') continue;
    const isMedia = e.matches(MEDIA);
    const rects = isMedia ? [e.getBoundingClientRect()] : ownTextRects(e);
    for (const r of rects) {
      const v = visibleRect(e, r, !isMedia);
      if (v && v.width > 2 && v.height > 2) boxes.push({ e, r: v });
    }
  }
  const cell = 128, grid = new Map();
  boxes.forEach((b, i) => {
    for (let gx = Math.floor(b.r.left / cell); gx <= Math.floor(b.r.right / cell); gx++)
      for (let gy = Math.floor(b.r.top / cell); gy <= Math.floor(b.r.bottom / cell); gy++) {
        const k = gx + ':' + gy; if (!grid.has(k)) grid.set(k, []); grid.get(k).push(i);
      }
  });
  const seen = new Set(); let pairs = 0;
  for (const ids of grid.values()) {
    for (let a = 0; a < ids.length; a++) for (let b = a + 1; b < ids.length; b++) {
      if (++pairs > o.maxPairs) break;
      const A = boxes[ids[a]], B = boxes[ids[b]];
      if (A.e === B.e || A.e.contains(B.e) || B.e.contains(A.e)) continue;
      const key = ids[a] < ids[b] ? ids[a] + '|' + ids[b] : ids[b] + '|' + ids[a];
      if (seen.has(key)) continue; seen.add(key);
      const i = inter(A.r, B.r);
      if (!i || i.width < 3 || i.height < 3) continue;
      const cx = (i.left + i.right) / 2, cy = (i.top + i.bottom) / 2;
      const stack = document.elementsFromPoint(cx, cy);
      const ia = stack.findIndex((s) => s === A.e || A.e.contains(s)), ib = stack.findIndex((s) => s === B.e || B.e.contains(s));
      const onTop = ia === -1 && ib === -1 ? null : (ib === -1 || (ia !== -1 && ia < ib)) ? 'a' : 'b';
      push({ check: 'collision', severity: 'medium', msg: 'Visible content overlaps other content (confirm on screenshot — may be intentional layering)',
        a: { sel: cssPath(A.e), text: label(A.e) }, b: { sel: cssPath(B.e), text: label(B.e) }, overlap: R(i), onTop });
    }
  }

  // 5. Occluded / overlapped controls (only within current viewport) ------
  for (const e of interactive) {
    const r = e.getBoundingClientRect();
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
    const v = visibleRect(e); if (!v) continue;
    const pts = [[0.5, 0.5], [0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]]
      .map(([fx, fy]) => [v.left + v.width * fx, v.top + v.height * fy])
      .filter(([x, y]) => x >= 0 && y >= 0 && x < vw && y < vh);
    let blocked = 0, by = null;
    for (const [x, y] of pts) {
      const hit = document.elementFromPoint(x, y);
      if (!hit || hit === e || e.contains(hit) || hit.contains(e)) continue;
      const lab = e.labels ? [...e.labels] : [];
      if (lab.some((l) => l === hit || l.contains(hit))) continue;
      blocked++; by = hit;
    }
    if (pts.length && blocked >= Math.ceil(pts.length / 2))
      push({ check: 'occluded-control', severity: 'high', msg: `Control is covered — ${blocked}/${pts.length} sample points hit another element`, sel: cssPath(e), text: label(e), coveredBy: cssPath(by), rect: R(r) });
    else if (blocked) push({ check: 'occluded-control', severity: 'low', msg: `Control partly covered (${blocked}/${pts.length} points)`, sel: cssPath(e), text: label(e), coveredBy: cssPath(by), rect: R(r) });
    // visual overlap by fixed/sticky layers, even with pointer-events:none
    for (const L of layers) {
      if (L.contains(e) || e.contains(L)) continue;
      const i = inter(v, L.getBoundingClientRect());
      if (i && i.width * i.height > 0.15 * v.width * v.height)
        push({ check: 'fixed-layer-overlap', severity: 'high', msg: `Fixed/sticky layer covers ${Math.round(100 * i.width * i.height / (v.width * v.height))}% of a control`, sel: cssPath(e), text: label(e), layer: cssPath(L), rect: R(r) });
    }
  }

  // 6. Target size (WCAG 2.5.8 AA: 24x24 or spacing exception) -------------
  const tgt = interactive.filter((e) => !(e.tagName === 'INPUT' && ['checkbox', 'radio'].includes(e.type) && e.labels && e.labels.length));
  const rects = tgt.map((e) => e.getBoundingClientRect());
  const small = (r) => r.width < o.minTarget || r.height < o.minTarget;
  const distToRect = (x, y, r) => Math.hypot(Math.max(r.left - x, 0, x - r.right), Math.max(r.top - y, 0, y - r.bottom));
  tgt.forEach((e, i) => {
    const r = rects[i]; if (!small(r)) return;
    const cs = getComputedStyle(e);
    if (cs.display === 'inline' && e.parentElement && (e.parentElement.innerText || '').trim().length > (e.innerText || '').trim().length + 20) return; // inline link in a sentence: exempt
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const conflict = tgt.some((f, j) => {
      if (j === i || f.contains(e) || e.contains(f)) return false;
      const q = rects[j];
      return small(q) ? Math.hypot(cx - (q.left + q.width / 2), cy - (q.top + q.height / 2)) < o.minTarget : distToRect(cx, cy, q) < o.minTarget / 2;
    });
    if (conflict) push({ check: 'target-size', severity: 'medium', msg: `Target ${Math.round(r.width)}x${Math.round(r.height)}px < ${o.minTarget}px and too close to another target (WCAG 2.5.8)`, sel: cssPath(e), text: label(e), rect: R(r) });
  });

  // 7. Images ---------------------------------------------------------------
  for (const img of all.filter((e) => e.tagName === 'IMG')) {
    const r = img.getBoundingClientRect();
    if (img.complete && img.naturalWidth === 0) { push({ check: 'image-broken', severity: 'high', msg: 'Image failed to load', sel: cssPath(img), src: img.currentSrc || img.src }); continue; }
    if (!img.naturalWidth) continue;
    const ics = getComputedStyle(img);
    const px = (k) => parseFloat(ics[k]) || 0;
    const cw = r.width - px('paddingLeft') - px('paddingRight') - px('borderLeftWidth') - px('borderRightWidth');
    const ch = r.height - px('paddingTop') - px('paddingBottom') - px('borderTopWidth') - px('borderBottomWidth');
    if (cw < 2 || ch < 2) continue;
    const isVector = /\.svg(\?|#|$)|^data:image\/svg/i.test(img.currentSrc || img.src);
    if (!isVector && cw > img.naturalWidth * 1.1) push({ check: 'image-upscaled', severity: 'low', msg: `Bitmap shown at ${Math.round(cw)}px but is only ${img.naturalWidth}px wide (blurry; worse on HiDPI)`, sel: cssPath(img) });
    const fit = ics.objectFit;
    const nr = img.naturalWidth / img.naturalHeight, rr = cw / ch;
    if (fit === 'fill' && Math.abs(nr - rr) / nr > 0.03) push({ check: 'image-distorted', severity: 'medium', msg: `Aspect ratio distorted (${nr.toFixed(2)} → ${rr.toFixed(2)}); use object-fit: cover/contain`, sel: cssPath(img) });
  }

  // 8. Text size ------------------------------------------------------------
  const tiny = new Set();
  for (const e of all) {
    if (!ownTextRects(e).length) continue;
    const fs = parseFloat(getComputedStyle(e).fontSize);
    if (fs < 12 && tiny.size < 30) { tiny.add(e); push({ check: 'small-text', severity: 'low', msg: `Text rendered at ${fs}px`, sel: cssPath(e), text: label(e) }); }
  }
  for (const e of all.filter((x) => x.matches('input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]),select,textarea'))) {
    const fs = parseFloat(getComputedStyle(e).fontSize);
    if (fs < 16) { push({ check: 'input-zoom-ios', severity: 'info', msg: `Form field font-size ${fs}px < 16px: iOS Safari zooms on focus. Fix with 16px text — never by disabling zoom`, sel: cssPath(e) }); break; }
  }
  return { viewport: { w: vw, h: vh }, scroll: { x: scrollX, y: scrollY }, docHeight: de.scrollHeight, findings: out };
}

// Keyboard walk helpers (run in page between Tab presses)
function focusProbe() {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return { none: true };
  const style = window.__uiaSig(el);
  const r = el.getBoundingClientRect();
  // clipped away by a collapsed / off-canvas ancestor (overflow hidden, width 0)?
  let clippedBy = null;
  { let a = el.parentElement, rect = { l: r.left, t: r.top, r: r.right, b: r.bottom };
    while (a && a !== document.documentElement) { const c = getComputedStyle(a);
      if (c.overflowX !== 'visible' || c.overflowY !== 'visible') { const q = a.getBoundingClientRect();
        rect = { l: Math.max(rect.l, q.left), t: Math.max(rect.t, q.top), r: Math.min(rect.r, q.right), b: Math.min(rect.b, q.bottom) };
        if (rect.r - rect.l < 1 || rect.b - rect.t < 1) { clippedBy = a; break; } }
      a = a.parentElement; } }
  const vw = document.documentElement.clientWidth, vh = innerHeight;
  // fraction of the focused element hidden by other elements (sampled grid)
  let hidden = 0, total = 0, by = null;
  for (let fx = 0.1; fx < 1; fx += 0.2) for (let fy = 0.1; fy < 1; fy += 0.2) {
    const x = r.left + r.width * fx, y = r.top + r.height * fy;
    total++;
    if (x < 0 || y < 0 || x >= vw || y >= vh) { hidden++; continue; }
    const hit = document.elementFromPoint(x, y);
    if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) { hidden++; by = hit; }
  }
  window.__uiaPrev = window.__uiaPrev || [];
  window.__uiaPrev.push(el);
  const id = el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '');
  const coveredBy = by ? (by.id ? '#' + by.id : by.tagName.toLowerCase() + (typeof by.className === 'string' && by.className ? '.' + by.className.trim().split(/\s+/)[0] : '')) : null;
  const nm = (n) => n ? (n.id ? '#' + n.id : n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\s+/)[0] : '')) : null;
  const scrollable = clippedBy && /(auto|scroll)/.test(getComputedStyle(clippedBy).overflowX + getComputedStyle(clippedBy).overflowY);
  if (clippedBy) return { scrollable, id, idx: window.__uiaPrev.length - 1, text: (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 50), style, hiddenFrac: 1, clippedBy: nm(clippedBy), coveredBy: null, rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) } };
  return { id, idx: window.__uiaPrev.length - 1, text: (el.getAttribute('aria-label') || el.innerText || el.value || '').trim().slice(0, 50), style, hiddenFrac: hidden / total, coveredBy, rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) } };
}
function installSig() {
  // focus "signature": own styles + ::before/::after + parent (covers :focus-within and pseudo-element rings)
  const K = ['outlineStyle', 'outlineWidth', 'outlineColor', 'boxShadow', 'borderColor', 'borderWidth', 'backgroundColor', 'textDecorationLine', 'color', 'transform'];
  window.__uiaSig = (el) => [getComputedStyle(el), getComputedStyle(el, '::before'), getComputedStyle(el, '::after'), el.parentElement ? getComputedStyle(el.parentElement) : null]
    .map((cs) => cs ? K.map((k) => cs[k]).join('|') : '').join('#');
}
function unfocusedStyle(idx) {
  const el = (window.__uiaPrev || [])[idx];
  if (!el || el === document.activeElement || el.contains(document.activeElement)) return null;
  return window.__uiaSig(el);
}

// Screenshot of a tracked element's box + 6px (focus rings are often drawn outside the box)
async function shotOf(page, idx) {
  const box = await page.evaluate((i) => {
    const el = (window.__uiaPrev || [])[i]; if (!el) return null;
    const r = el.getBoundingClientRect(), m = 6, vw = document.documentElement.clientWidth, vh = innerHeight;
    const x = Math.max(0, r.left - m), y = Math.max(0, r.top - m);
    const w = Math.min(vw, r.right + m) - x, h = Math.min(vh, r.bottom + m) - y;
    return w > 2 && h > 2 ? { x, y, width: w, height: h } : null;
  }, idx);
  if (!box) return null;
  try { return await page.screenshot({ clip: box, animations: 'disabled', caret: 'hide' }); } catch { return null; }
}

// Stress modes ---------------------------------------------------------------
const STRESS = {
  none: null,
  // WCAG 1.4.12 Text Spacing override — content must not be clipped/overlapped
  textspacing: `*{line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important}p{margin-bottom:2em!important}`,
  rtl: 'rtl',
  pseudo: 'pseudo', // ~40% longer, accented strings (simulates German/Finnish expansion + diacritics)
};
function applyPseudo() {
  const map = { a: 'á', e: 'é', i: 'í', o: 'ö', u: 'ü', A: 'Å', E: 'É', O: 'Ø', c: 'ç', n: 'ñ' };
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode: (n) => (n.textContent.trim() && !n.parentElement.closest('script,style,code,pre,textarea') ? 1 : 2) });
  const nodes = []; while (w.nextNode()) nodes.push(w.currentNode);
  for (const n of nodes) {
    const t = n.textContent;
    const pad = Math.max(2, Math.round(t.trim().length * 0.4));
    const words = []; let left = pad; while (left > 0) { const k = Math.min(left, 6); words.push('ẍ'.repeat(k)); left -= k; }
    n.textContent = t.replace(/[aeiouAEOcn]/g, (c) => map[c] || c).replace(/(\S)(\s*)$/, `$1 ${words.join(' ')}$2`);
  }
  for (const el of document.querySelectorAll('[placeholder]')) el.setAttribute('placeholder', el.getAttribute('placeholder') + ' ẍẍẍẍẍẍ');
}

// ---------------------------------------------------------------------------
async function auditOne(browser, url, cfg, w, scheme, stress) {
  const ctx = await browser.newContext({
    viewport: { width: w, height: w < 600 ? 780 : 900 }, deviceScaleFactor: 1, colorScheme: scheme, reducedMotion: 'reduce',
    ...(w < 600 ? { isMobile: true, hasTouch: true } : {}), ...(cfg.storage ? { storageState: cfg.storage } : {}),
  });
  const page = await ctx.newPage();
  const consoleErrors = [], failed = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e).slice(0, 300)));
  page.on('requestfailed', (r) => failed.push(`${r.failure()?.errorText} ${r.url().slice(0, 200)}`));
  await page.addInitScript(() => {
    window.__cls = 0;
    try { new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch {}
  });
  try { await page.goto(url, { waitUntil: cfg.wait, timeout: cfg.timeout }); }
  catch (e) { try { await page.goto(url, { waitUntil: 'load', timeout: cfg.timeout }); } catch (e2) { await ctx.close(); return { url, w, scheme, stress, error: String(e2).slice(0, 300) }; } }
  await page.waitForTimeout(800);
  const cls = await page.evaluate(() => window.__cls);
  // freeze motion so screenshots are deterministic
  await page.addStyleTag({ content: '*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition:none!important;caret-color:transparent!important}' });
  if (STRESS[stress] === 'rtl') await page.evaluate(() => { document.documentElement.dir = 'rtl'; });
  else if (STRESS[stress] === 'pseudo') await page.evaluate(applyPseudo);
  else if (STRESS[stress]) await page.addStyleTag({ content: STRESS[stress] });
  await page.waitForTimeout(200);

  const tag = `${slug(url)}__${w}__${scheme}__${stress}`;
  const shot = path.join(cfg.out, 'screens', tag + '.png');
  await page.screenshot({ path: shot, fullPage: true }).catch(() => {});

  // run audit at successive scroll positions (fixed layers move relative to content)
  const findings = [];
  const docH = await page.evaluate(() => document.documentElement.scrollHeight);
  const vh = page.viewportSize().height;
  const steps = Math.min(12, Math.ceil(docH / vh));
  for (let s = 0; s < steps; s++) {
    await page.evaluate((y) => window.scrollTo(0, y), s * vh);
    await page.waitForTimeout(120);
    const res = await page.evaluate(inPageAudit, {});
    for (const f of res.findings) {
      if (s > 0 && !['occluded-control', 'fixed-layer-overlap'].includes(f.check)) continue; // scroll-independent checks once
      findings.push({ ...f, scrollY: res.scroll.y });
    }
  }
  await page.evaluate(() => window.scrollTo(0, 0));

  // keyboard walk: focus visibility, obscured focus, traps
  if (cfg.keyboard) {
    await page.evaluate(installSig);
    const seq = [];
    for (let i = 0; i < cfg.maxTabs; i++) {
      await page.keyboard.press('Tab');
      await page.waitForTimeout(40);
      const p = await page.evaluate(focusProbe);
      if (p.none) { if (seq.length) break; else continue; }
      if (seq.length) {
        const prev = seq[seq.length - 1];
        const un = await page.evaluate(unfocusedStyle, prev.idx);
        if (un !== null && !prev.skipVis) {
          const unShot = prev.shot ? await shotOf(page, prev.idx) : null;
          const samePixels = prev.shot && unShot && prev.shot.equals(unShot);
          if (samePixels) findings.push({ check: 'focus-invisible', severity: 'high', msg: 'Focused and unfocused renderings are pixel-identical — no visible focus indicator (WCAG 2.4.7)', sel: prev.id, text: prev.text });
          else if (!prev.shot && un === prev.style) findings.push({ check: 'focus-invisible', severity: 'medium', msg: 'No computed-style change on focus (pixel check unavailable — confirm visually)', sel: prev.id, text: prev.text });
        }
      }
      if (p.clippedBy && p.scrollable) findings.push({ check: 'focus-obscured', severity: 'medium', msg: `Focused element is scrolled out of view inside scroll container ${p.clippedBy} and the browser did not reveal it`, sel: p.id, text: p.text, rect: p.rect });
      else if (p.clippedBy) findings.push({ check: 'focus-obscured', severity: 'high', msg: `Focusable element is invisible — clipped away by a collapsed/off-canvas container (${p.clippedBy}). Remove it from the tab order while hidden (inert / display:none / visibility:hidden)`, sel: p.id, text: p.text, rect: p.rect });
      else if (p.hiddenFrac >= 0.99) findings.push({ check: 'focus-obscured', severity: 'high', msg: 'Focused element is entirely hidden (WCAG 2.4.11 fail)', sel: p.id, text: p.text, coveredBy: p.coveredBy, rect: p.rect });
      else if (p.hiddenFrac >= 0.3) findings.push({ check: 'focus-obscured', severity: 'medium', msg: `Focused element ${Math.round(p.hiddenFrac * 100)}% hidden (WCAG 2.4.12 AAA; usually caused by sticky header/footer — use scroll-padding)`, sel: p.id, text: p.text, coveredBy: p.coveredBy, rect: p.rect });
      p.skipVis = !!p.clippedBy || p.hiddenFrac >= 0.99; // already reported as obscured; pixels would be meaningless
      p.shot = p.skipVis ? null : await shotOf(page, p.idx);
      seq.push(p);
      // trap heuristic: last 12 focus stops cycle among <= 3 distinct elements
      if (seq.length >= 12) {
        const last = new Set(seq.slice(-12).map((x) => x.id + x.rect.x + x.rect.y));
        if (last.size <= 3) { findings.push({ check: 'focus-trap', severity: 'high', msg: 'Tab key cycles among ≤3 elements — possible keyboard trap (OK only inside an open modal with an Escape/close path)', items: [...last] }); break; }
      }
    }
  }

  // axe-core (optional)
  try {
    const axePath = require.resolve('axe-core/axe.min.js');
    await page.addScriptTag({ path: axePath });
    const axe = await page.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 5).map((n) => n.target.join(' ')) })));
    for (const v of axe) findings.push({ check: 'axe:' + v.id, severity: v.impact === 'critical' || v.impact === 'serious' ? 'high' : 'medium', msg: v.help, items: v.nodes });
  } catch { /* axe-core not installed: report it in summary */ }

  if (cls > 0.1) findings.push({ check: 'cls', severity: cls > 0.25 ? 'high' : 'medium', msg: `Cumulative Layout Shift during load = ${cls.toFixed(3)} (good < 0.1)` });
  for (const c of consoleErrors.slice(0, 10)) findings.push({ check: 'console-error', severity: 'medium', msg: c });
  for (const r of failed.slice(0, 10)) findings.push({ check: 'request-failed', severity: 'low', msg: r });

  await ctx.close();
  return { url, w, scheme, stress, screenshot: path.relative(cfg.out, shot), cls, findings: dedupe(findings) };
}

const slug = (u) => u.replace(/^https?:\/\//, '').replace(/^file:\/\//, '').replace(/[^a-z0-9]+/gi, '_').slice(-60);
function dedupe(fs) {
  const seen = new Set();
  return fs.filter((f) => { const k = [f.check, f.sel, f.a?.sel, f.b?.sel, f.layer, f.msg].join('¦'); if (seen.has(k)) return false; seen.add(k); return true; });
}

function summarize(results, cfg, axeAvailable) {
  const lines = [`# UI audit summary`, ``, `Generated ${new Date().toISOString()} · widths ${cfg.widths.join(', ')} · schemes ${cfg.schemes.join(', ')} · stress ${cfg.stress.join(', ')}`, ``];
  if (!axeAvailable) lines.push(`> axe-core not installed — contrast/ARIA/name checks NOT run. \`npm i -D axe-core\` and re-run.`, ``);
  lines.push(`> Every row is a candidate. Confirm each against its screenshot before acting; intentional layering exists.`, ``);
  const byCheck = {};
  for (const r of results) for (const f of r.findings || []) (byCheck[f.check] ||= []).push({ ...f, ctx: `${r.w}px/${r.scheme}/${r.stress}` });
  const order = { high: 0, medium: 1, low: 2, info: 3 };
  lines.push(`| check | high | medium | low | info |`, `|---|---|---|---|---|`);
  for (const [k, arr] of Object.entries(byCheck).sort()) {
    const c = (s) => arr.filter((f) => f.severity === s).length;
    lines.push(`| ${k} | ${c('high')} | ${c('medium')} | ${c('low')} | ${c('info')} |`);
  }
  for (const r of results) {
    lines.push(``, `## ${r.url} — ${r.w}px · ${r.scheme} · ${r.stress}`);
    if (r.error) { lines.push(`ERROR: ${r.error}`); continue; }
    lines.push(`Screenshot: \`${r.screenshot}\` · CLS ${r.cls?.toFixed(3)}`);
    const fs = [...r.findings].sort((a, b) => order[a.severity] - order[b.severity]).slice(0, 60);
    for (const f of fs) {
      const where = f.sel ? ` \`${f.sel}\`` : f.a ? ` \`${f.a.sel}\` ↔ \`${f.b.sel}\`` : '';
      const extra = f.coveredBy ? ` (covered by \`${f.coveredBy}\`)` : f.layer ? ` (layer \`${f.layer}\`)` : f.items ? ` → ${f.items.slice(0, 4).map((i) => '`' + (i.sel || i) + '`').join(', ')}` : '';
      lines.push(`- **${f.severity}** ${f.check}:${where} — ${f.msg}${f.text ? ` “${f.text}”` : ''}${extra}`);
    }
    if (r.findings.length > 60) lines.push(`- … ${r.findings.length - 60} more in results.json`);
  }
  return lines.join('\n');
}

// Self-test fixture: every check must fire here, or the audit is not trustworthy.
const FIXTURE = `<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;font:16px system-ui} header{position:sticky;top:0;height:64px;background:#222;color:#fff;z-index:10}
.wide{width:1400px;height:20px;background:#eee}.btn{width:90px;white-space:nowrap;overflow:visible;display:inline-block;border:1px solid}
.clip{width:120px;height:20px;overflow:hidden}.chat{position:fixed;right:8px;bottom:8px;width:120px;height:120px;background:#06c;border-radius:50%}
.save{position:fixed;right:20px;bottom:30px} .tiny a{display:inline-block;width:14px;height:14px;font-size:10px}
.abs{position:relative}.abs span{position:absolute;top:0;left:0;color:red} button:focus{outline:none}
img.st{width:300px;height:100px}</style></head><body><header>Header</header>
<div class="wide"></div><p><span class="btn">Einstellungsänderungenspeichern</span></p>
<div class="clip">This text is far too long to fit in this tiny fixed box and will be cut</div>
<div class="abs"><p>Paragraph text under an overlay</p><span>OVERLAPPING LABEL</span></div>
<div class="tiny"><a href="#1">x</a><a href="#2">y</a><a href="#3">z</a></div>
<img class="st" alt="stretched" src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='50' height='50'><rect width='50' height='50' fill='red'/></svg>">
<img alt="broken" src="does-not-exist.png" width="40" height="40">
<p><button id="noring">No ring</button></p><p id="cleanp">A clean paragraph with a <a id="goodlink" href="#g">good link</a> inside it.</p>
<div style="height:1200px"></div><button id="lowbtn">No focus ring</button><div style="height:40px"></div>
<button class="save">Save changes</button><div class="chat"></div>
<div style="position:fixed;left:0;right:0;bottom:0;height:70px;background:#333;color:#fff">We use cookies</div></body></html>`;

// ---------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const flag = (n, d) => { const a = args.find((x) => x.startsWith(`--${n}=`)); return a ? a.split('=').slice(1).join('=') : d; };
  const cfg = {
    out: path.resolve(flag('out', 'ui-audit-out')),
    widths: flag('widths', '320,375,768,1024,1440').split(',').map(Number),
    schemes: flag('schemes', 'light,dark').split(','),
    stress: flag('stress', 'none,textspacing,pseudo').split(','),
    wait: flag('wait', 'networkidle'), timeout: +flag('timeout', 30000), maxTabs: +flag('max-tabs', 150),
    keyboard: !args.includes('--no-keyboard'), storage: flag('storage', null),
  };
  let urls = args.filter((a) => !a.startsWith('--'));
  if (args.includes('--selftest')) {
    fs.mkdirSync(cfg.out, { recursive: true });
    const fx = path.join(cfg.out, 'selftest-fixture.html'); fs.writeFileSync(fx, FIXTURE);
    urls = ['file://' + fx]; cfg.widths = [1024]; cfg.schemes = ['light']; cfg.stress = ['none']; cfg.wait = 'load';
  }
  if (!urls.length) { console.error('Usage: node ui-audit.mjs <url...> [--selftest] [options]'); process.exit(2); }
  for (const s of cfg.stress) if (!(s in STRESS)) { console.error('Unknown stress mode: ' + s); process.exit(2); }
  fs.mkdirSync(path.join(cfg.out, 'screens'), { recursive: true });
  let axeAvailable = true; try { require.resolve('axe-core/axe.min.js'); } catch { axeAvailable = false; }

  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const results = [];
  for (const url of urls) for (const w of cfg.widths) for (const scheme of cfg.schemes) for (const stress of cfg.stress) {
    process.stderr.write(`audit ${url} @${w} ${scheme} ${stress}\n`);
    results.push(await auditOne(browser, url, cfg, w, scheme, stress));
  }
  await browser.close();
  fs.writeFileSync(path.join(cfg.out, 'results.json'), JSON.stringify(results, null, 2));
  fs.writeFileSync(path.join(cfg.out, 'SUMMARY.md'), summarize(results, cfg, axeAvailable));

  if (args.includes('--selftest')) {
    const want = ['horizontal-overflow', 'text-spill', 'text-clipped', 'collision', 'fixed-layer-overlap', 'occluded-control', 'target-size', 'image-distorted', 'image-broken', 'small-text', 'focus-invisible', 'focus-obscured'];
    const got = new Set(results.flatMap((r) => (r.findings || []).map((f) => f.check)));
    const missing = want.filter((c) => !got.has(c));
    // negative controls: known-good elements must NOT be flagged
    const all = results.flatMap((r) => r.findings || []);
    const falsePos = all.filter((f) => JSON.stringify(f).includes('goodlink') || JSON.stringify(f).includes('cleanp'));
    const ok = !missing.length && !falsePos.length;
    console.log(missing.length ? `SELFTEST FAIL — checks that did not fire: ${missing.join(', ')}` : `positive controls: all ${want.length} checks fired`);
    console.log(falsePos.length ? `SELFTEST FAIL — false positives on clean controls: ${falsePos.map((f) => f.check).join(', ')}` : 'negative controls: no false positives on known-good elements');
    console.log(ok ? 'SELFTEST PASS' : 'SELFTEST FAIL');
    process.exit(ok ? 0 : 1);
  }
  const total = results.reduce((n, r) => n + (r.findings?.length || 0), 0);
  console.log(`Done: ${results.length} runs, ${total} candidate findings → ${path.join(cfg.out, 'SUMMARY.md')}`);
}
main().catch((e) => { console.error(e); process.exit(1); });
