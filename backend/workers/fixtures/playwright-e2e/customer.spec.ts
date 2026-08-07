import { test, expect } from "@playwright/test";

test("customer search to detail", async ({ page }) => {
  await page.goto("/customers/search");
  await page.fill('[data-testid="customer-id-input"]', "CUS-1001");
  await page.click('[data-testid="customer-search-submit"]');
  await expect(page).toHaveURL(/\/customers\/CUS-1001/);
});
