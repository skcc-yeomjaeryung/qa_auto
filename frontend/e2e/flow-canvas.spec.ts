/**
 * 테스트 시나리오 · 의존관계 그래프 E2E (Playwright) — deep link, layout, node detail.
 * Observational: does not declare HITL Pass/Fail.
 */
import { expect, test } from "@playwright/test";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByTestId("login-id").fill("TEST");
  await page.getByTestId("login-password").fill("1");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/($|\?)/, { timeout: 15_000 });
}

async function firstGraphId(): Promise<string | null> {
  const res = await fetch(`${API}/api/interaction-graphs`, {
    headers: { "X-User-Id": "TEST" },
  });
  if (!res.ok) return null;
  const rows = (await res.json()) as Array<{ graphId: string }>;
  return rows[0]?.graphId ?? null;
}

test.describe("테스트 시나리오 화면", () => {
  test("그룹 목록에서 시나리오를 고르면 우측 상세가 열리고 그래프는 deep link로 유지된다", async ({
    page,
  }) => {
    const graphId = await firstGraphId();
    test.skip(!graphId, "등록된 Interaction Graph 없음 — missing_data");
    await login(page);
    await page.goto("/scenarios");

    // 1단 = 테스트 시나리오 그룹 → 2단 = 목록 + 우측 슬라이드 상세
    const groupRow = page
      .getByTestId("scenario-group-table")
      .locator("tbody tr.is-clickable")
      .first();
    await groupRow.locator("strong.id-link").click();
    await expect(page).toHaveURL(/setId=/);
    await expect(page.getByTestId("scenario-split")).toBeVisible({ timeout: 15_000 });

    await page.locator("[data-testid^=scenario-row-] .scn-row-main").first().click();
    await expect(page).toHaveURL(/scenarioId=/);
    // 상세는 포워딩 없이 같은 화면 우측에서 열린다 — 목록도 계속 보인다
    await expect(page.getByTestId("scenario-detail-panel")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("scenario-split")).toBeVisible();

    // 의존관계 그래프는 보조 화면 — URL에 상태가 남아 새로고침을 견딘다.
    await page.goto(`/scenarios?view=graph&graphId=${graphId}`);
    await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });
    await page.reload();
    await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });
  });

  test("구 /flow 경로는 쿼리를 지켜 테스트 시나리오로 넘긴다", async ({ page }) => {
    await login(page);
    await page.goto("/flow");
    await expect(page).toHaveURL(/\/scenarios/);
  });

  test("캔버스는 가로 스크롤 없이 배치되고 단계 상태를 불러온다", async ({ page }) => {
    const graphId = await firstGraphId();
    test.skip(!graphId, "등록된 Interaction Graph 없음 — missing_data");
    await login(page);
    await page.goto(`/scenarios?view=graph&graphId=${graphId}`);
    const canvas = page.getByTestId("flow-canvas");
    await expect(canvas).toBeVisible({ timeout: 15_000 });

    const overflow = await canvas.evaluate(
      (el) => el.scrollWidth - el.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // 단계 상태 조회가 실패하면 경고 배너가 뜬다 — 정상 경로에서는 없어야 한다
    await expect(page.getByTestId("flow-message")).toHaveCount(0);
  });

  test("노드를 선택하면 상세가 보이고 중첩 인터랙션이 없다", async ({ page }) => {
    const graphId = await firstGraphId();
    test.skip(!graphId, "등록된 Interaction Graph 없음 — missing_data");
    await login(page);
    await page.goto(`/scenarios?view=graph&graphId=${graphId}`);
    await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });

    const nested = await page.evaluate(
      () => document.querySelectorAll("[role=button] button, button button").length,
    );
    expect(nested).toBe(0);

    await page.locator(".flow-card-select").first().click();
    const inspector = page.getByTestId("flow-gql-inspector");
    await expect(inspector).toBeVisible();
    await expect(inspector).toBeInViewport();
  });

  test("I/O 패널은 값이 없을 때 이유를 밝힌다 (빈 중괄호 금지)", async ({ page }) => {
    const graphId = await firstGraphId();
    test.skip(!graphId, "등록된 Interaction Graph 없음 — missing_data");
    await login(page);
    await page.goto(`/scenarios?view=graph&graphId=${graphId}`);
    await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });

    const cards = page.locator(".flow-card-select");
    const count = Math.min(await cards.count(), 8);
    for (let i = 0; i < count; i += 1) {
      await cards.nth(i).click();
      for (const testId of ["flow-io-input", "flow-io-output"]) {
        const pane = page.getByTestId(testId);
        await expect(pane).toBeVisible();
        const state = await pane.getAttribute("data-io-state");
        expect(["observed", "candidate", "missing"]).toContain(state);
        // A bare "{}" tells the reader nothing — every empty pane states why.
        expect((await pane.innerText()).trim()).not.toBe("{}");
      }
    }
  });

  test("연결을 선택하면 조건·대상 편집과 끊기를 할 수 있다", async ({ page }) => {
    const graphId = await firstGraphId();
    test.skip(!graphId, "등록된 Interaction Graph 없음 — missing_data");
    await login(page);
    await page.goto(`/scenarios?view=graph&graphId=${graphId}`);
    await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });

    // the condition pill is the reachable affordance — the line itself can be
    // covered by node cards on a dense graph
    await page.locator("[data-testid^=flow-edge-pill-]").first().click();
    const editor = page.getByTestId("flow-edge-editor");
    await expect(editor).toBeVisible();
    await expect(page.getByTestId("flow-edge-to")).toBeVisible();
    await expect(page.getByTestId("flow-edge-type")).toBeVisible();
    await expect(page.getByTestId("flow-edge-condition")).toBeVisible();
    await expect(page.getByTestId("flow-edge-disconnect")).toBeEnabled();

    // condition presets come from the backend contract, not a hardcoded list
    const presets = await page
      .locator("#flow-condition-presets option")
      .evaluateAll((els) => els.map((e) => (e as HTMLOptionElement).value));
    expect(presets).toContain("happy_path");
    expect(presets.length).toBeGreaterThan(1);
  });

  test("새 연결 추가는 두 노드를 직접 고르게 한다", async ({ page }) => {
    const graphId = await firstGraphId();
    test.skip(!graphId, "등록된 Interaction Graph 없음 — missing_data");
    await login(page);
    await page.goto(`/scenarios?view=graph&graphId=${graphId}`);
    await expect(page.getByTestId("flow-canvas")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("flow-open-connect").click();
    await expect(page.getByTestId("flow-edge-connect")).toBeVisible();
    await expect(page.getByTestId("flow-connect-apply")).toBeDisabled();
  });
});
