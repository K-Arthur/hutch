#!/usr/bin/env node
/*
 * Stamp website/index.html asset references with a content hash.
 *
 * The site ships a committed build (website/app.css) and static stylesheets
 * whose filenames never change, so a browser that cached an earlier build
 * keeps serving it. Rewriting the query string from the file's own bytes makes
 * every rebuild a new URL without renaming files or adding a runtime cost.
 *
 * Runs as the second half of `npm run build:css`.
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const htmlPath = join(root, "website", "index.html");
const assets = ["tokens.css", "app.css", "styles.css", "site.js"];

const hash = (file) =>
  createHash("sha256").update(readFileSync(file)).digest("hex").slice(0, 8);

let html = readFileSync(htmlPath, "utf8");
let stamped = 0;

for (const name of assets) {
  let digest;
  try {
    digest = hash(join(root, "website", name));
  } catch {
    continue; // asset not present; nothing to stamp
  }
  const re = new RegExp(`((?:href|src)=")${name.replace(".", "\\.")}(?:\\?v=[a-f0-9]+)?(")`, "g");
  html = html.replace(re, (_m, open, close) => {
    stamped += 1;
    return `${open}${name}?v=${digest}${close}`;
  });
}

writeFileSync(htmlPath, html);
console.log(`stamped ${stamped} asset reference(s) in website/index.html`);
