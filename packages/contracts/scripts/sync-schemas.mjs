import { cp, mkdir, readdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(packageRoot, "../../docs/03.계약과예시/schemas");
const destination = resolve(packageRoot, "schemas");
await mkdir(destination, { recursive: true });

for (const file of await readdir(source)) {
  if (file.endsWith(".json")) await cp(resolve(source, file), resolve(destination, file));
}
