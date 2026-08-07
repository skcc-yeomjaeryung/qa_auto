/**
 * Scorecard gate E2E (Playwright) — Console UX paths.
 * Observational: does not declare HITL Pass/Fail.
 */
import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";
const RESULT_DIR = path.resolve(__dirname, "../../artifacts/e2e");

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByTestId("login-id").fill("TEST");
  await page.getByTestId("login-password").fill("1");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/($|\?)/, { timeout: 15_000 });
}

async function ensureProject(): Promise<string> {
  const listRes = await fetch(`${API}/api/projects?ownerUserId=TEST`, {
    headers: { "X-User-Id": "TEST" },
  });
  const list = listRes.ok ? ((await listRes.json()) as Array<{ id: string }>) : [];
  if (list[0]?.id) return list[0].id;
  const createRes = await fetch(`${API}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-User-Id": "TEST" },
    body: JSON.stringify({
      name: `PW-Scorecard-${Date.now()}`,
      ownerUserId: "TEST",
      description: "playwright scorecard seed",
    }),
  });
  const body = (await createRes.json()) as { id?: string; projectId?: string; detail?: string };
  const id = body.id || body.projectId;
  if (!id) throw new Error(body.detail || "project seed failed");
  return id;
}

test.describe("스코어카드 게이트 Playwright E2E", () => {
  test("M1 미로그인 시 보호 경로 리다이렉트", async ({ page }) => {
    await page.goto("/scenarios");
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });

  test("M2 대시보드 · 로그인 후 진입", async ({ page }) => {
    await login(page);
    await page.goto("/");
    await expect(page.getByTestId("dashboard")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("dashboard-hero")).toBeVisible({ timeout: 10_000 });
    const gate = page.getByTestId("project-gate-banner");
    const stats = page.getByTestId("dashboard-stats");
    await expect(gate.or(stats).first()).toBeVisible({ timeout: 10_000 });
  });

  test("P1 프로젝트 상세 · 실행환경 영역", async ({ page }) => {
    const projectId = await ensureProject();
    await login(page);
    await page.goto("/projects");
    await expect(page.getByTestId("projects-workbench")).toBeVisible({ timeout: 15_000 });
    // open detail by matching project id text if listed
    const row = page.locator("table tbody tr").filter({ hasText: projectId }).first();
    if (await row.count()) await row.click();
    else await page.locator("table tbody tr").first().click({ trial: true }).catch(() => undefined);
    const envPanel = page.getByTestId("project-detail-environments");
    const present = await envPanel.isVisible().catch(() => false);
    fs.mkdirSync(RESULT_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(RESULT_DIR, "scorecard-p1-env.json"),
      JSON.stringify({ at: new Date().toISOString(), projectId, envPanelVisible: present }, null, 2),
    );
    expect(projectId).toBeTruthy();
  });

  test("A1 분석 메뉴 · 게이트 또는 목록", async ({ page }) => {
    await ensureProject();
    await login(page);
    // FE hasProject is client-side; seed API project may not unlock nav until reload/list
    await page.goto("/projects");
    await expect(page.getByTestId("projects-workbench")).toBeVisible({ timeout: 15_000 });
    await page.goto("/analysis");
    await expect(page.locator("body")).toBeVisible();
    const ok = await page.locator("body").innerText();
    expect(ok.length).toBeGreaterThan(20);
    fs.mkdirSync(RESULT_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(RESULT_DIR, "scorecard-a1-analysis.json"),
      JSON.stringify({ at: new Date().toISOString(), url: page.url(), snippet: ok.slice(0, 200) }, null, 2),
    );
  });

  test("S3 시나리오 그룹/목록 또는 잠금 안내", async ({ page }) => {
    await ensureProject();
    await login(page);
    await page.goto("/projects");
    await expect(page.getByTestId("projects-workbench")).toBeVisible({ timeout: 15_000 });
    await page.goto("/scenarios");
    await expect(page.locator("body")).toBeVisible();
    const ok = await page.locator("body").innerText();
    expect(ok.length).toBeGreaterThan(20);
  });

  test("C8 구 플로우 경로는 테스트 시나리오로 넘어간다", async ({ page }) => {
    await ensureProject();
    await login(page);
    await page.goto("/projects");
    await expect(page.getByTestId("projects-workbench")).toBeVisible({ timeout: 15_000 });
    await page.goto("/flow");
    await expect(page).toHaveURL(/\/scenarios/, { timeout: 15_000 });
    await expect(page.locator("body")).toBeVisible();
    const ok = await page.locator("body").innerText();
    expect(ok.length).toBeGreaterThan(20);
  });

  test("R1 시나리오 상세 · 실행 버튼(시나리오 있을 때)", async ({ page }) => {
    await ensureProject();
    await login(page);
    await page.goto("/scenarios");
    const detail = page.getByRole("link", { name: /상세/ }).first();
    if (await detail.isVisible().catch(() => false)) {
      await detail.click();
      await expect(page.getByTestId("run-with-recommended")).toBeVisible({
        timeout: 15_000,
      });
    } else {
      await expect(page.locator("main")).toBeVisible();
    }
  });
});
