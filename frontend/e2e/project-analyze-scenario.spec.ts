import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";
const RESULT_DIR = path.resolve(__dirname, "../../artifacts/e2e");

function findLocalRepo(): string | null {
  const envPath = process.env.E2E_LOCAL_REPO?.trim();
  if (envPath && fs.existsSync(envPath)) return envPath;
  const workspaces = path.resolve(__dirname, "../../.data/workspaces");
  if (!fs.existsSync(workspaces)) return null;
  const dirs = fs.readdirSync(workspaces);
  const scored: Array<{ full: string; score: number }> = [];
  for (const name of dirs) {
    const full = path.join(workspaces, name);
    if (!fs.statSync(full).isDirectory()) continue;
    let score = 0;
    if (fs.existsSync(path.join(full, "kubernetes-manifests"))) score += 5;
    if (fs.existsSync(path.join(full, "mvnw")) || fs.existsSync(path.join(full, "pom.xml"))) score += 3;
    if (fs.existsSync(path.join(full, "package.json"))) score += 3;
    if (fs.existsSync(path.join(full, "src"))) score += 1;
    if (fs.existsSync(path.join(full, "README.md"))) score += 1;
    if (score > 0) scored.push({ full, score });
  }
  scored.sort((a, b) => b.score - a.score);
  return scored[0]?.full ?? null;
}

test.describe.configure({ mode: "serial" });

test("프로젝트 등록(git/local) → 분석 → 시나리오 생성", async ({ page }) => {
  fs.mkdirSync(RESULT_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const projectName = `E2E-${stamp.slice(0, 19)}`;
  const localRepo = findLocalRepo();
  const githubUrl =
    process.env.E2E_GITHUB_URL ??
    "https://github.com/GoogleCloudPlatform/bank-of-anthos.git";

  const result: Record<string, unknown> = {
    startedAt: new Date().toISOString(),
    projectName,
    mode: localRepo ? "local" : "github",
    location: localRepo || githubUrl,
    steps: [] as Array<Record<string, unknown>>,
  };

  const note = (step: string, ok: boolean, detail?: string) => {
    (result.steps as Array<Record<string, unknown>>).push({
      step,
      ok,
      detail,
      at: new Date().toISOString(),
    });
  };

  await page.goto("/login");
  await page.getByTestId("login-id").fill("TEST");
  await page.getByTestId("login-password").fill("1");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/($|\?)/, { timeout: 15_000 });
  note("login", true);

  await page.goto("/projects");
  await expect(page.getByTestId("projects-workbench")).toBeVisible();
  await page.getByTestId("project-create-open").click();
  await page.getByTestId("project-name-input").fill(projectName);
  await page.getByTestId("project-create-btn").click();
  await expect(page.getByTestId("github-url-input").or(page.getByTestId("local-path-input"))).toBeVisible({
    timeout: 20_000,
  });
  note("project-create", true);

  if (localRepo) {
    await page.locator("select").first().selectOption("local");
    await page.getByTestId("local-path-input").fill(localRepo);
  } else {
    await page.getByTestId("github-url-input").fill(githubUrl);
  }
  await page.getByTestId("repo-connect-btn").click();
  // STEP 3 = 실행 환경 등록(Health Check). 기본 프리셋(Pilot Sandbox)을 그대로 등록한다.
  const envSave = page.getByTestId("env-save-btn");
  await expect(envSave).toBeVisible({ timeout: 180_000 });
  note("repo-connect", true, localRepo || githubUrl);
  await envSave.click();
  await expect(page.getByTestId("project-confirm-summary")).toBeVisible({ timeout: 120_000 });
  note("env-register", true);

  // 「프로젝트 분석」은 분석 + 시나리오 생성까지 수행하고 결과 화면으로 이동한다.
  await page.getByRole("button", { name: "프로젝트 분석" }).click();
  await expect(page).toHaveURL(/\/(scenarios|analysis)/, { timeout: 300_000 });
  note("analyze", true, page.url());

  await page.goto("/analysis");
  await expect(page.getByTestId("analysis-workbench")).toBeVisible({ timeout: 60_000 });
  const repoRow = page.locator(".enterprise-table tbody tr").first();
  await expect(repoRow).toBeVisible({ timeout: 60_000 });
  // 저장소 행을 열면 소스 탐색이 펼쳐진다 (분석 산출물 확인)
  await repoRow.locator("strong.id-link").click();
  await expect(page.getByTestId("source-explorer")).toBeVisible({ timeout: 60_000 });
  note("analysis-source-explorer", true);

  await page.goto("/scenarios");
  await expect(page.getByTestId("scenario-group-table")).toBeVisible({ timeout: 30_000 });
  const setRow = page.locator('[data-testid="scenario-group-table"] tbody tr.is-clickable').first();
  await expect(setRow).toBeVisible({ timeout: 30_000 });
  await setRow.locator("strong.id-link").click();
  // 그룹을 열면 목록 + 우측 상세 2단이 뜬다
  await expect(page.getByTestId("scenario-split")).toBeVisible({ timeout: 30_000 });
  note("scenarios-page", true);

  // API smoke: catalog + scenarios
  const analyses = await page.request.get(`${API}/api/console/analyses`);
  expect(analyses.ok()).toBeTruthy();
  const scenarios = await page.request.get(`${API}/api/scenarios`);
  expect(scenarios.ok()).toBeTruthy();
  const analysisJson = await analyses.json();
  const scenarioJson = await scenarios.json();
  result.analysisCount = Array.isArray(analysisJson) ? analysisJson.length : null;
  result.scenarioCount = Array.isArray(scenarioJson)
    ? scenarioJson.length
    : (scenarioJson as { items?: unknown[] })?.items?.length ?? null;
  // BoA/multi-flow: customer-search 템플릿 1건이 아니라 다건이어야 한다
  expect(Number(result.scenarioCount || 0)).toBeGreaterThan(2);
  result.finishedAt = new Date().toISOString();
  result.status = "observed_complete";

  const outFile = path.join(RESULT_DIR, `project-analyze-scenario-${stamp}.json`);
  fs.writeFileSync(outFile, JSON.stringify(result, null, 2));
  await page.screenshot({ path: path.join(RESULT_DIR, `project-analyze-scenario-${stamp}.png`), fullPage: true });
});
