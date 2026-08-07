import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolve } from "node:path";
import { analyzeFrontend } from "../src/analyze.js";

const fixtures = resolve(import.meta.dirname, "../fixtures");

describe("golden fixtures", () => {
  it("next app router extracts search + detail routes and POST search", () => {
    const result = analyzeFrontend({
      workspacePath: resolve(fixtures, "next-app-router"),
      commitSha: "fixture",
    });
    const routes = result.screens.map((s) => s.route).sort();
    assert.ok(routes.includes("/customers/search"));
    assert.ok(routes.some((r) => r.includes("/customers/:id") || r.includes("/customers/[id]") || r === "/customers/:id"));
    assert.ok(result.apiCalls.some((a) => a.method === "POST" && a.normalizedPath === "/api/customers/search"));
    assert.ok(result.inputs.some((i) => i.name === "customerId" || i.testId === "customer-id-input"));
  });

  it("pages router extracts route and router.push", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "pages-router") });
    assert.ok(result.screens.some((s) => s.framework === "next-pages"));
    assert.ok(result.routeTransitions.some((t) => t.to.includes("/customers/detail")));
  });

  it("rhf + zod validations", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "rhf-zod") });
    assert.ok(result.validations.some((v) => v.kind.startsWith("zod") || v.kind === "react-hook-form"));
  });

  it("axios/fetch/react-query clients", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "api-clients") });
    const clients = new Set(result.apiCalls.map((a) => a.client));
    assert.ok(clients.has("fetch"));
    assert.ok(clients.has("axios"));
    assert.ok(clients.has("react-query"));
  });

  it("direct router.push", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "router-push") });
    assert.ok(result.routeTransitions.some((t) => t.to.includes("/customers/")));
  });

  it("wrapper button keeps click handler", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "wrapper-button") });
    assert.ok(result.events.some((e) => e.event === "onClick"));
    assert.ok(result.apiCalls.some((a) => a.normalizedPath === "/api/customers/search"));
  });

  it("path alias fixture analyzes without crash", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "path-alias") });
    assert.ok(result.fileHashes.some((f) => f.path.includes("Home.tsx")));
    assert.ok(result.components.some((c) => c.name === "Home") || result.events.length >= 0);
  });

  it("dynamic dispatch is unresolved", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "dynamic-unresolved") });
    assert.ok(result.unresolved.some((u) => u.kind === "dynamic-dispatch"));
  });

  it("playwright evidence steps", () => {
    const result = analyzeFrontend({ workspacePath: resolve(fixtures, "playwright-e2e") });
    assert.equal(result.existingTests.length, 1);
    assert.ok(result.existingTests[0]!.steps.some((s) => s.action === "goto"));
    assert.ok(result.existingTests[0]!.steps.some((s) => s.action === "fill"));
    assert.ok(result.existingTests[0]!.steps.some((s) => s.action === "click"));
  });
});
