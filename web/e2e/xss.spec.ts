import { expect, test, type Page } from "@playwright/test";
import { startWorkspace } from "./helpers";

// L22: every string from an upload is shown as text. A file name, a header and cell
// values carry markup; none of it may become an element or run. Kept in step with
// tests/e2e/serve.py.
const FILE = '<img src=x onerror="window.__xss=1">.csv';
const HEADER = "<script>window.__xss=1</script>";
const CELL = "<img src=x onerror=window.__xss=1>";

async function assertInert(page: Page): Promise<void> {
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  await expect(page.locator("#app img")).toHaveCount(0);
  await expect(page.locator("#app script")).toHaveCount(0);
}

async function uploadText(page: Page, text: string): Promise<void> {
  const stored = page.waitForResponse(
    (r) => r.url().includes("/api/workspace/files") && r.request().method() === "PUT",
  );
  await page.locator("#files").setInputFiles({ name: FILE, mimeType: "text/csv", buffer: Buffer.from(text) });
  expect((await stored).status()).toBe(200);
  await expect(page.locator(".files li")).toHaveCount(1);
}

test("user strings render as text, never as markup", async ({ page }) => {
  page.on("dialog", () => {
    throw new Error("a dialog opened: markup ran");
  });
  await startWorkspace(page);

  // A failing file: its name and a quoted cell value appear in the Check report.
  await uploadText(page, `id,${HEADER}\n${CELL},a\n${CELL},b\n`);
  await expect(page.locator(".file-name")).toHaveText(FILE);
  await page.getByRole("button", { name: "Check my files" }).click();
  const report = page.locator(".file-report.fail");
  await expect(report).toContainText(FILE);
  await expect(report).toContainText(`the ID '${CELL}' is also on row 2`);
  await assertInert(page);

  // The same file fixed: the header shows on Confirm, the cells in the answer.
  await page.getByRole("button", { name: "Back to upload" }).click();
  await uploadText(page, `id,${HEADER}\n1,${CELL}\n2,${HEADER}\n`);
  await page.getByRole("button", { name: "Check my files" }).click();
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await expect(page.locator("table.fields")).toContainText(`from column “${HEADER}”`);
  await assertInert(page);
  await page.getByRole("button", { name: "Confirm and continue" }).click();

  await page.locator("#question").fill("Show the odd table");
  await page.getByRole("main").getByRole("button", { name: "Ask" }).click();
  await expect(page.locator("table.answer td")).toHaveText(["1", CELL, "2", HEADER]);
  await assertInert(page);
});
