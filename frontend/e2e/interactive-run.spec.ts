/**
 * Phase 13 — 건별 시나리오 테스트 UX E2E (Playwright 보완 경로).
 * 관측만 수행하며 HITL Pass/Fail를 단정하지 않는다.
 * 시나리오가 없는 환경에서는 해당 검증을 skip한다.
 */
import { expect, test, type Page } from "@playwright/test";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByTestId("login-id").fill("TEST");
  await page.getByTestId("login-password").fill("1");
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/($|\?)/, { timeout: 15_000 });
}

async function firstScenarioId(): Promise<string | null> {
  const res = await fetch(`${API}/api/scenarios`, { headers: { "X-User-Id": "TEST" } });
  if (!res.ok) return null;
  const rows = (await res.json()) as Array<{ scenarioId: string }>;
  return rows[0]?.scenarioId ?? null;
}

/** 상세는 3탭 구조 — 실행·증적은 「예상 테스트 결과」 탭에 있다 */
async function openResultTab(page: Page) {
  const tab = page.getByTestId("scenario-tab-result");
  await expect(tab).toBeVisible({ timeout: 20_000 });
  await tab.click();
}

test.describe("건별 시나리오 테스트 UX", () => {
  test("상세는 3탭으로 나뉘고 기술 정보는 접힌 상태로 둔다", async ({ page }) => {
    const scenarioId = await firstScenarioId();
    test.skip(!scenarioId, "시나리오가 없는 환경");
    await login(page);
    await page.goto(`/scenarios/${scenarioId}`);

    // 첫 진입은 「화면 구성 확인」 — 무엇을 확인하는 테스트인지 먼저 읽는다
    await expect(page.getByTestId("scenario-panel-composition")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("scenario-tab-composition")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.getByTestId("scenario-run-console")).toHaveCount(0);

    // 개발자용 케이스 분석·단계 정의는 접힌 상태
    await expect(page.getByTestId("scenario-technical-more")).not.toHaveAttribute("open", "");

    // 실행 흐름 탭
    await page.getByTestId("scenario-tab-flow").click();
    await expect(page.getByTestId("scenario-flow-board")).toBeVisible({ timeout: 20_000 });
  });

  test("추천 요약이 폼 강제 없이 노출되고 실행 CTA가 1클릭 거리에 있다", async ({ page }) => {
    const scenarioId = await firstScenarioId();
    test.skip(!scenarioId, "시나리오가 없는 환경");
    await login(page);
    await page.goto(`/scenarios/${scenarioId}`);
    await openResultTab(page);

    const console_ = page.getByTestId("scenario-run-console");
    await expect(console_).toBeVisible({ timeout: 20_000 });

    // A → Backend → B 요약과 여정 Type 2 스텝퍼가 상단에 있다
    await expect(page.getByTestId("run-flow-strip")).toBeVisible();
    await expect(page.getByTestId("scenario-journey-type2")).toBeVisible();

    // 기본 진입 시 전체 편집 폼을 펼치지 않는다
    await expect(page.getByTestId("toggle-input-edit")).toHaveAttribute("aria-expanded", "false");
    await expect(page.locator("#run-console-inputs")).toHaveCount(0);

    // 기본 CTA는 「추천값으로 실행」 — 진입 후 1클릭
    const cta = page.getByTestId("run-with-recommended");
    await expect(cta).toBeVisible();
    await expect(cta).toBeEnabled();

    // 실행 ID·버전 같은 기술 정보는 접힌 상태로 둔다
    const technical = page.getByTestId("run-technical-more");
    if (await technical.count()) {
      await expect(technical).not.toHaveAttribute("open", "");
    }
  });

  test("확인 필요 항목만 강조하고 destructive 여부를 명시한다", async ({ page }) => {
    const scenarioId = await firstScenarioId();
    test.skip(!scenarioId, "시나리오가 없는 환경");
    await login(page);
    await page.goto(`/scenarios/${scenarioId}`);
    await openResultTab(page);
    await expect(page.getByTestId("scenario-run-console")).toBeVisible({ timeout: 20_000 });

    await expect(page.getByTestId("uncertain-items")).toBeVisible();
    await expect(page.getByTestId("destructive-flag")).toBeVisible();
  });

  test("접근성 — 편집 입력에 라벨이 연결되고 키보드로 실행 CTA에 도달한다", async ({ page }) => {
    const scenarioId = await firstScenarioId();
    test.skip(!scenarioId, "시나리오가 없는 환경");
    await login(page);
    await page.goto(`/scenarios/${scenarioId}`);
    await openResultTab(page);
    await expect(page.getByTestId("scenario-run-console")).toBeVisible({ timeout: 20_000 });

    const toggle = page.getByTestId("toggle-input-edit");
    if (await toggle.isEnabled()) {
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-expanded", "true");

      const editor = page.locator("#run-console-inputs");
      await expect(editor).toBeVisible();

      // 편집 폼의 모든 컨트롤은 접근 가능한 이름을 가진다
      const controls = editor.locator("input, select");
      const count = await controls.count();
      expect(count).toBeGreaterThan(0);
      for (let i = 0; i < count; i += 1) {
        const name = await controls.nth(i).evaluate((el) => {
          const id = el.getAttribute("id");
          const label = id ? document.querySelector(`label[for="${id}"]`) : null;
          return label?.textContent?.trim() || el.getAttribute("aria-label") || "";
        });
        expect(name.length).toBeGreaterThan(0);
      }
    } else {
      // 화면 구성 확인처럼 입력이 없는 케이스 — 편집할 값이 없다고 화면이 말해야 한다
      await expect(page.getByTestId("no-input-needed")).toBeVisible();
    }

    // 키보드 포커스로 실행 CTA에 도달할 수 있다
    const cta = page.getByTestId("run-with-recommended");
    await cta.focus();
    await expect(cta).toBeFocused();
  });
});
