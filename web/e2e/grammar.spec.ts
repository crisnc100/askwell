import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { SAMPLE, startWorkspace } from "./helpers";

// Grammar v0.2 with the fake model: a ratio and a two-date series on the sample data,
// each with its formula shown in the trace.
async function readyToAsk(page: Page): Promise<void> {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles(
    ["customers.csv", "orders.csv", "order_items.csv", "products.csv"].map((f) => path.join(SAMPLE, f)),
  );
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  await expect(page.getByRole("heading", { name: "Ask a question" })).toBeVisible();
}

async function ask(page: Page, question: string): Promise<void> {
  await page.locator("#question").fill(question);
  await page.getByRole("main").getByRole("button", { name: "Ask" }).click();
  await expect(page.locator("table.answer")).toBeVisible();
}

test("a ratio and a two-date series answer, with their formulas in the trace", async ({ page }) => {
  await readyToAsk(page);

  await ask(page, "What share of orders are paid?");
  await expect(page.locator("table.answer th")).toHaveText(["paid", "total", "pct_paid"]);
  const [paid, total, pct] = (await page.locator("table.answer td").allTextContents()).map(Number);
  expect(total).toBe(60);
  expect(paid).toBeGreaterThan(0);
  expect(pct).toBeCloseTo((paid * 100) / total, 6);
  await page.getByText("How this answer was made").click();
  await expect(page.locator(".formulas")).toHaveText([
    "pct_paid = paid ÷ total × 100 (empty when total is 0)",
  ]);

  await ask(page, "Orders per month by order date and by customer signup date");
  await expect(page.locator("table.answer th")).toHaveText(["period", "placed", "by_signup"]);
  const rows = page.locator("table.answer tbody tr");
  expect(await rows.count()).toBeGreaterThan(1);
  const placed = await page.locator("table.answer tbody tr td:nth-child(2)").allTextContents();
  expect(placed.map(Number).reduce((a, b) => a + b, 0)).toBe(60);
  await page.getByText("How this answer was made").click();
  await expect(page.locator(".formulas li")).toHaveText([
    "placed: count of rows, by order_date",
    "by_signup: count of rows, by customers.signup_date",
  ]);
});
