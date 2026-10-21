import { spawn } from "node:child_process";
import { watch } from "node:fs";

const watchers = [
  ["website/src/input.css", "website/app.css", []],
  ["website/styles.css", "website/styles.min.css", ["--minify"]],
];
const children = watchers.map(([input, output, extra]) => spawn("tailwindcss", [
  "-i", input, "-o", output, ...extra, "--watch",
], { stdio: "inherit" }));

let stampTimer;
let stamping = false;
let stampAgain = false;
function stampAssets() {
  clearTimeout(stampTimer);
  stampTimer = setTimeout(() => {
    if (stamping) { stampAgain = true; return; }
    stamping = true;
    const child = spawn(process.execPath, ["scripts/stamp_site_assets.mjs"], { stdio: "inherit" });
    child.on("exit", () => {
      stamping = false;
      if (stampAgain) { stampAgain = false; stampAssets(); }
    });
  }, 150);
}

watch("website", (_event, filename) => {
  if (filename === "app.css" || filename === "styles.min.css") stampAssets();
});

function stop() {
  for (const child of children) child.kill("SIGTERM");
  process.exit(0);
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
for (const child of children) child.on("exit", code => {
  if (code && code !== 0) process.exitCode = code;
});
