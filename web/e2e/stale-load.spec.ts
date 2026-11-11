import { expect, test } from "@playwright/test";
import path from "node:path";
import { SAMPLE, startWorkspace } from "./helpers";

// A page load that answers late never overwrites what a newer load (and the person's
// edits since) put on the page.
test("a late Confirm load does not undo newer edits", async ({ page }) => {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles(
    ["customers.csv", "orders.csv", "order_items.csv", "products.csv"].map((f) => path.join(SAMPLE, f)),
  );
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();
  await expect(page.getByText("Every file passed and your data is loaded.")).toBeVisible();

  // The first fields response is held until the newer edit has been made, then let
  // through, so it always answers last.
  let release: () => void = () => undefined;
  const held = new Promise<void>((resolve) => (release = resolve));
  let calls = 0;
  let answered = 0;
  await page.route("**/api/workspace/fields", async (route) => {
    calls += 1;
    if (calls === 1) await held;
    await route.continue();
    answered += 1;
  });
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await expect.poll(() => calls).toBe(1);
  await page.getByRole("navigation").getByRole("button", { name: "Confirm" }).click();
  const preview = page.locator("#prompt-preview");
  await expect(preview).toContainText("## customers");
  await page.locator('[data-key="orders.status"][data-role="description"]').fill("kept words");
  await expect(preview).toContainText("kept words");
  expect(answered).toBe(1); // only the newer load has answered so far

  const stale = page.waitForResponse((r) => r.url().includes("/api/workspace/fields"));
  release();
  await stale;
  await expect.poll(() => answered).toBe(2);
  // Give the page a turn to act on the stale answer before the next edit.
  await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 100)));

  await page.locator('[data-key="products.category"][data-role="description"]').fill("later words");
  await expect(preview).toContainText("later words");
  await expect(preview).toContainText("kept words");
});
