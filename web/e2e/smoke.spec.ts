import { expect, test } from "@playwright/test";
import path from "node:path";
import { lastExportedRequest, SAMPLE, startWorkspace } from "./helpers";

// L17: Prepare -> Upload the sample -> Check -> Confirm (hide one field, add one
// description) -> Ask, with a fake model. The request the model got shows both edits.
test("the sample data goes from upload to an answer", async ({ page }) => {
  const description = "Where the order is: paid, shipped or refunded.";
  await startWorkspace(page);

  await page.locator("#files").setInputFiles(
    ["customers.csv", "orders.csv", "order_items.csv", "products.csv"].map((f) => path.join(SAMPLE, f)),
  );
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();

  await expect(page.getByText("Every file passed and your data is loaded.")).toBeVisible();
  await expect(page.locator(".file-report.pass")).toHaveCount(4);
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();

  await expect(page.getByRole("heading", { name: "Confirm what the model may see" })).toBeVisible();
  const preview = page.locator("#prompt-preview");
  await expect(preview).toContainText("## customers");
  await page.locator('[data-key="customers.name"][data-role="hide"]').check();
  await page.locator('[data-key="orders.status"][data-role="description"]').fill(description);
  await expect(preview).toContainText(description);
  await expect(preview).not.toContainText("- contact_email");
  await page.getByRole("button", { name: "Confirm and continue" }).click();

  await expect(page.getByRole("heading", { name: "Ask a question" })).toBeVisible();
  await page.locator("#question").fill("How many orders?");
  await page.getByRole("main").getByRole("button", { name: "Ask" }).click();
  await expect(page.locator("table.answer td")).toHaveText(["60"]);
  await page.getByText("How this answer was made").click();
  await expect(page.locator(".trace")).toContainText("SELECT");

  const system = lastExportedRequest().messages[0].content;
  expect(system).toContain(`- status: text — ${description}`);
  const customers = system.split("## customers")[1].split("## ")[0];
  expect(customers).not.toContain("- name:");
  expect(system).not.toContain("contact_email");

  // The bookmark link reopens the workspace where it was left.
  const link = (await page.locator(".workspace .link").first().textContent()) ?? "";
  expect(link).toMatch(/\/#ws=[0-9a-f]{32}$/);
  await page.goto("about:blank");
  await page.goto(link);
  await expect(page.getByRole("heading", { name: "Ask a question" })).toBeVisible();
});
