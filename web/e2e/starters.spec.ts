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

// While an ask runs, neither a starter nor the Ask button can send another, so two
// answers never overwrite each other.
test("starters and Ask are disabled while a question is being answered", async ({ page }) => {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles(
    ["customers.csv", "orders.csv", "order_items.csv", "products.csv"].map((f) => path.join(SAMPLE, f)),
  );
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  const starters = page.locator("#starters button");
  await expect(starters.first()).toBeVisible();

  let asks = 0;
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/workspace/ask", async (route) => {
    asks += 1;
    await held;
    await route.continue();
  });

  const first = (await starters.first().textContent()) ?? "";
  await starters.first().click();
  await expect(page.locator(".result")).toContainText("Working…");
  for (const button of await starters.all()) await expect(button).toBeDisabled();
  const ask = page.getByRole("main").getByRole("button", { name: "Ask", exact: true });
  await expect(ask).toBeDisabled();
  await page.locator("#question").press("Enter");
  expect(asks).toBe(1);

  release();
  await expect(page.locator(".result")).not.toContainText("Working…");
  await expect(page.locator("#question")).toHaveValue(first);
  for (const button of await starters.all()) await expect(button).toBeEnabled();
  await expect(ask).toBeEnabled();
  expect(asks).toBe(1);
});
