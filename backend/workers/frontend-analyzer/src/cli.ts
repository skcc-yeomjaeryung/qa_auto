import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { analyzeFrontend } from "./analyze.js";

function usage(): never {
  console.error(
    "Usage: tsx src/cli.ts analyze <workspacePath> [--out <file>] [--commit <sha>]",
  );
  process.exit(2);
}

const args = process.argv.slice(2);
const cmd = args[0];
if (cmd !== "analyze") usage();

const workspacePath = args[1] ? resolve(args[1]) : usage();
let out: string | null = null;
let commit: string | null = null;
for (let i = 2; i < args.length; i += 1) {
  if (args[i] === "--out") out = args[++i] ?? null;
  else if (args[i] === "--commit") commit = args[++i] ?? null;
}

const progressPath = process.env.ANALYSIS_PROGRESS_PATH
  ? resolve(process.env.ANALYSIS_PROGRESS_PATH)
  : null;
const progressTotal = Number.parseInt(process.env.ANALYSIS_PROGRESS_TOTAL ?? "0", 10);
const progressOffset = Number.parseInt(process.env.ANALYSIS_PROGRESS_OFFSET ?? "0", 10);
const writeProgress = (completed: number, workerTotal: number) => {
  if (!progressPath) return;
  const total = progressTotal > 0 ? progressTotal : progressOffset + workerTotal;
  mkdirSync(dirname(progressPath), { recursive: true });
  writeFileSync(
    progressPath,
    JSON.stringify({ completed: Math.min(total, progressOffset + completed), failed: 0, total }),
    "utf8",
  );
};

const result = analyzeFrontend({ workspacePath, commitSha: commit, onProgress: writeProgress });
const json = JSON.stringify(result, null, 2);
if (out) {
  const abs = resolve(out);
  mkdirSync(dirname(abs), { recursive: true });
  writeFileSync(abs, json, "utf8");
  console.log(JSON.stringify({ ok: true, out: abs, screens: result.screens.length }));
} else {
  console.log(json);
}
