import { spawn } from "node:child_process";

const children = [
  ["app/src/input.css", "src/hutch/server/static/ui.css"],
  ["app/src/model-switcher.css", "src/hutch/server/static/model-switcher.css"],
].map(([input, output]) => spawn("tailwindcss", ["-i", input, "-o", output, "--watch"], { stdio: "inherit" }));

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) child.kill("SIGTERM");
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
for (const child of children) {
  child.on("error", error => { console.error(error.message); stop(1); });
  child.on("exit", code => { if (!stopping) stop(code || 1); });
}
