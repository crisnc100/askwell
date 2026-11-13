import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { SAMPLE, startWorkspace } from "./helpers";

// Stable answers with the fake model: grouping by the drafted name column shows each
// customer's ID, a top 2 that cuts a tie says so, and clearing the name column on
// Confirm groups by the name alone. In the sample, the top customers have 8, 7 and 7
// orders.
async function toConfirm(page: Page): Promise<void> {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles(
    ["customers.csv", "orders.csv", "order_items.csv", "products.csv"].map((f) => path.join(SAMPLE, f)),
  );
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await expect(page.getByRole("heading", { name: "Confirm what the model may see" })).toBeVisible();
}

async function askTopTwo(page: Page): Promise<void> {
  await page.locator("#question").fill("Top 2 customers by orders");
  await page.getByRole("main").getByRole("button", { name: "Ask" }).click();
  await expect(page.locator("table.answer")).toBeVisible();
}

test("a name column keeps customers apart, and a cut tie is named", async ({ page }) => {
  await toConfirm(page);
  const label = page.locator('[data-table="customers"][data-role="label"]');
  await expect(label).toHaveValue("name");
  await expect(page.getByLabel("Name column").first()).toBeVisible();
  await expect(page.locator('[data-table="order_items"][data-role="label"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Confirm and continue" }).click();

  await askTopTwo(page);
  await expect(page.locator("table.answer th")).toHaveText(["customers__id", "customers__name", "orders"]);
  await expect(page.locator("table.answer tbody tr")).toHaveCount(2);
  await expect(page.locator(".tie-note")).toHaveText("More rows tie with the last one shown.");
});

test("clearing the name column groups by the name alone", async ({ page }) => {
  await toConfirm(page);
  await page.locator('[data-table="customers"][data-role="label"]').selectOption("");
  await page.getByRole("button", { name: "Confirm and continue" }).click();

  await askTopTwo(page);
  await expect(page.locator("table.answer th")).toHaveText(["customers__name", "orders"]);
});
