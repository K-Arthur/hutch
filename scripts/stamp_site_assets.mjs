#!/usr/bin/env node
/*
 * Stamp every local asset reference in website/index.html with a content hash.
 *
 * The site ships a committed build and static images/stylesheets/fonts whose
 * filenames never change, so a browser that cached an earlier build can keep
 * serving stale UI or product captures. Rewriting local URLs from each file's
 * own bytes makes every rebuild a new URL without renaming files or runtime cost.
 *
 * Runs as the second half of `npm run build:css`.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const htmlPath = join(root, "website", "index.html");
const siteRoot = join(root, "website");

const hash = (file) =>
  createHash("sha256").update(readFileSync(file)).digest("hex").slice(0, 8);

let html = readFileSync(htmlPath, "utf8");
let stamped = 0;

function stampUrl(value) {
  const fragmentAt = value.indexOf("#");
  const fragment = fragmentAt >= 0 ? value.slice(fragmentAt) : "";
  const beforeFragment = fragmentAt >= 0 ? value.slice(0, fragmentAt) : value;
  const queryAt = beforeFragment.indexOf("?");
  const pathname = queryAt >= 0 ? beforeFragment.slice(0, queryAt) : beforeFragment;
  const query = queryAt >= 0 ? beforeFragment.slice(queryAt + 1) : "";
  if (!pathname || pathname.startsWith("/") || /^[a-z][a-z0-9+.-]*:/i.test(pathname)) return value;

  const file = resolve(siteRoot, pathname);
  const fromRoot = relative(siteRoot, file);
  if (!fromRoot || fromRoot === ".." || fromRoot.startsWith(`..${sep}`) || !existsSync(file)) return value;

  const params = new URLSearchParams(query);
  params.set("v", hash(file));
  stamped += 1;
  return `${pathname}?${params.toString()}${fragment}`;
}

function stampSrcset(value) {
  return value.split(",").map((candidate) => {
    const parts = candidate.trim().split(/\s+/);
    if (!parts[0]) return candidate;
    parts[0] = stampUrl(parts[0]);
    return parts.join(" ");
  }).join(", ");
}

html = html.replace(/\b(href|src|srcset)=("|')([^"']*)("|')/g, (_m, attr, quote, value, endQuote) => {
  const stampedValue = attr === "srcset" ? stampSrcset(value) : stampUrl(value);
  return `${attr}=${quote}${stampedValue}${endQuote}`;
});

writeFileSync(htmlPath, html);
console.log(`stamped ${stamped} local asset reference(s) in website/index.html`);
