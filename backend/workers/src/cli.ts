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

const result = analyzeFrontend({ workspacePath, commitSha: commit });
const json = JSON.stringify(result, null, 2);
if (out) {
  const abs = resolve(out);
  mkdirSync(dirname(abs), { recursive: true });
  writeFileSync(abs, json, "utf8");
  console.log(JSON.stringify({ ok: true, out: abs, screens: result.screens.length }));
} else {
  console.log(json);
}
