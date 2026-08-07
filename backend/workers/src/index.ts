import { access } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve } from "node:path";
import { analyzeFrontend } from "./analyze.js";

export { analyzeFrontend } from "./analyze.js";
export type { FrontendAnalysisResult } from "./types.js";

export async function health() {
  const contractsPath = resolve(import.meta.dirname, "../../../packages/contracts/schemas");
  let contractsAvailable = false;
  try {
    await access(contractsPath, constants.R_OK);
    contractsAvailable = true;
  } catch {
    // Analyzer can still start before the contracts package has been installed.
  }
  return { status: "ok", service: "frontend-analyzer", contractsAvailable, analyzer: "ts-morph" };
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  console.log(JSON.stringify(await health()));
}
