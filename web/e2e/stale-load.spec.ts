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

  let calls = 0;
  await page.route("**/api/workspace/fields", async (route) => {
    calls += 1;
    if (calls === 1) await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await page.getByRole("navigation").getByRole("button", { name: "Confirm" }).click();
  const preview = page.locator("#prompt-preview");
  await expect(preview).toContainText("## customers");
  await page.locator('[data-key="orders.status"][data-role="description"]').fill("kept words");
  await expect(preview).toContainText("kept words");

  await page.waitForTimeout(2000); // the first, slow load answers now
  await page.locator('[data-key="products.category"][data-role="description"]').fill("later words");
  await expect(preview).toContainText("later words");
  await expect(preview).toContainText("kept words");
});
