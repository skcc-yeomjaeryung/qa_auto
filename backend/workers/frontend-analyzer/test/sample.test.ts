import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { describe, it } from "node:test";
import { resolve } from "node:path";
import { analyzeFrontend } from "../src/analyze.js";

const sample = resolve(
  import.meta.dirname,
  "../../../../sample-targets/customer-portal-fe",
);

describe("sample-targets customer-portal-fe gate", () => {
  it("extracts A search, customerId rules, POST search, B route, playwright", { skip: !existsSync(sample) }, () => {
    const result = analyzeFrontend({
      workspacePath: sample,
      commitSha: "sample-local",
    });

    assert.ok(
      result.screens.some((s) => s.route === "/customers/search"),
      "A screen route missing",
    );
    assert.ok(
      result.screens.some((s) => s.route.includes("/customers/:customerId") || s.route === "/customers/:customerId"),
      "B screen route missing",
    );
    assert.ok(
      result.components.some((c) => c.name === "SearchPage" || c.name === "DetailPage"),
      "main components missing",
    );
    assert.ok(
      result.inputs.some((i) => i.testId === "customer-id-input"),
      "customerId input missing",
    );
    assert.ok(
      result.validations.some(
        (v) =>
          (v.field === "customerId" || v.expression.includes("CUS-")) &&
          (v.kind.includes("zod") || v.required),
      ),
      "customerId validation missing",
    );
    assert.ok(
      result.events.some((e) => e.event === "onSubmit" && e.handlerResolved),
      "submit handler missing",
    );
    assert.ok(
      result.apiCalls.some(
        (a) => a.method === "POST" && a.normalizedPath === "/api/customers/search",
      ),
      "POST /api/customers/search missing",
    );
    assert.ok(
      result.routeTransitions.some((t) => t.to.includes("/customers/")),
      "B route transition missing",
    );
    assert.ok(
      result.existingTests.some((t) => t.framework === "playwright" && t.steps.length > 0),
      "playwright evidence missing",
    );
    assert.ok(result.commitSha === "sample-local");
    assert.ok(result.screens.every((s) => s.evidence.file && s.evidence.line >= 1));
    assert.ok(Array.isArray(result.unresolved));
  });
});
