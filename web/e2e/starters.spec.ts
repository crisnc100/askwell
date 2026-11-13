import { expect, test } from "@playwright/test";
import path from "node:path";
import { SAMPLE, startWorkspace } from "./helpers";

// After Confirm, the Ask page offers starter questions made from the visitor's own
// columns. Clicking one asks it.
test("the Ask page offers 3 to 5 starter questions from the workspace's own columns", async ({ page }) => {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles(
    ["customers.csv", "orders.csv", "order_items.csv", "products.csv"].map((f) => path.join(SAMPLE, f)),
  );
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  await expect(page.getByRole("heading", { name: "Ask a question" })).toBeVisible();

  const starters = page.locator("#starters button");
  await expect(starters.first()).toBeVisible();
  const count = await starters.count();
  expect(count).toBeGreaterThanOrEqual(3);
  expect(count).toBeLessThanOrEqual(5);
  await expect(page.locator("#starters")).toContainText("How many customers are there by city?");

  const first = (await starters.first().textContent()) ?? "";
  await starters.first().click();
  await expect(page.locator("#question")).toHaveValue(first);
  await expect(page.locator(".result")).not.toContainText("Working…");
  await expect(page.locator(".result")).not.toBeEmpty();
  // No counter or remaining-quota text anywhere on the page.
  await expect(page.locator("#app")).not.toContainText(/remaining|left today|per hour|an hour/i);
});
