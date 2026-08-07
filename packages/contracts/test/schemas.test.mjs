import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import test from "node:test";

const schemaDirectory = resolve(import.meta.dirname, "../schemas");

test("all published schemas parse as JSON", async () => {
  const schemas = (await readdir(schemaDirectory)).filter((file) => file.endsWith(".json"));
  assert.ok(schemas.length >= 7);
  await Promise.all(schemas.map(async (file) => JSON.parse(await readFile(resolve(schemaDirectory, file), "utf8"))));
});
