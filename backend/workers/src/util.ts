import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import type { Evidence } from "./types.js";

const SKIP_DIRS = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".next",
  "coverage",
  ".turbo",
  "out",
]);

export function listSourceFiles(root: string): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      if (SKIP_DIRS.has(entry)) continue;
      const full = join(dir, entry);
      const st = statSync(full);
      if (st.isDirectory()) {
        walk(full);
        continue;
      }
      if (/\.(tsx?|jsx?|mjs|cjs)$/.test(entry)) {
        out.push(full);
      }
    }
  };
  walk(root);
  return out;
}

export function rel(root: string, file: string): string {
  return relative(root, file).split(sep).join("/");
}

export function sha256File(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function evidence(
  file: string,
  line: number,
  extractor: string,
  confidence: number,
): Evidence {
  return { file, line, extractor, confidence };
}

export function normalizeApiPath(raw: string): string {
  let value = raw.trim();
  value = value.replace(/^['"`]/, "").replace(/['"`]$/, "");
  // strip origin
  try {
    if (/^https?:\/\//i.test(value)) {
      const url = new URL(value);
      value = url.pathname;
    }
  } catch {
    // keep as-is
  }
  const idx = value.indexOf("/api/");
  if (idx >= 0) value = value.slice(idx);
  if (!value.startsWith("/")) value = `/${value}`;
  return value.replace(/\/+$/, "") || "/";
}

export function slug(parts: string[]): string {
  return parts
    .join("-")
    .replace(/[\\/]+/g, "_")
    .replace(/[^a-zA-Z0-9:_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 120);
}

export function literalText(node: { getText(): string } | undefined): string | null {
  if (!node) return null;
  const text = node.getText().trim();
  const m = text.match(/^['"`]([\s\S]*)['"`]$/);
  return m ? m[1]! : text;
}
