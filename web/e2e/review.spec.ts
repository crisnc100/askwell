import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { SAMPLE, startWorkspace } from "./helpers";

const SAMPLE_FILES = ["customers.csv", "orders.csv", "order_items.csv", "products.csv"];

async function toConfirm(page: Page): Promise<void> {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles(SAMPLE_FILES.map((f) => path.join(SAMPLE, f)));
  await expect(page.locator(".files li")).toHaveCount(4);
  await page.getByRole("button", { name: "Check my files" }).click();
  await page.getByRole("button", { name: "Next: confirm your fields" }).click();
  await expect(page.locator("#prompt-preview")).toContainText("## customers");
}

async function newWorkspace(page: Page): Promise<string> {
  const response = await page.request.post("/api/workspaces", { data: {} });
  expect(response.status()).toBe(201);
  return ((await response.json()) as { id: string }).id;
}

test("the Share box and the saved edits never disagree", async ({ page }) => {
  await toConfirm(page);
  const share = page.locator('[data-key="customers.city"][data-role="share"]');
  const hide = page.locator('[data-key="customers.city"][data-role="hide"]');
  const preview = page.locator("#prompt-preview");
  await share.check();
  await expect(preview).toContainText("Hillcrest");
  await hide.check();
  await expect(preview).not.toContainText("Hillcrest");
  await page.getByRole("button", { name: "Confirm and continue" }).click();
  await expect(page.getByRole("heading", { name: "Ask a question" })).toBeVisible();

  await page.getByRole("navigation").getByRole("button", { name: "Confirm" }).click();
  await expect(preview).toContainText("## customers");
  await hide.uncheck();
  await expect(share).toBeEnabled();
  await expect(share).not.toBeChecked();
  await page.waitForTimeout(600);
  await expect(preview).not.toContainText("Hillcrest");
});

test("changing the link's workspace switches the page to it", async ({ page }) => {
  const first = await newWorkspace(page);
  const second = await newWorkspace(page);
  const put = await page.request.put("/api/workspace/files", {
    headers: { "X-Workspace-Id": first, "X-File-Name": "only-in-first.csv" },
    data: Buffer.from("id\n1\n"),
  });
  expect(put.status()).toBe(200);
  await page.goto(`/#ws=${first}`);
  await expect(page.locator(".file-name")).toHaveText(["only-in-first.csv"]);
  await page.evaluate((id) => (location.hash = `#ws=${id}`), second);
  await expect(page.locator(".workspace .link")).toContainText(second);
  await expect(page.locator(".file-name")).toHaveCount(0);
});

test("a slow preview never replaces a newer one", async ({ page }) => {
  await toConfirm(page);
  let calls = 0;
  await page.route("**/api/workspace/preview", async (route) => {
    calls += 1;
    if (calls === 1) await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  const description = page.locator('[data-key="orders.status"][data-role="description"]');
  await description.fill("older words");
  await page.waitForTimeout(500);
  await description.fill("newer words");
  await page.waitForTimeout(2000);
  const preview = page.locator("#prompt-preview");
  await expect(preview).toContainText("newer words");
  await expect(preview).not.toContainText("older words");
});

test("a batch with one refused file keeps the others and says which failed", async ({ page }) => {
  await startWorkspace(page);
  await page.locator("#files").setInputFiles([
    { name: "first.csv", mimeType: "text/csv", buffer: Buffer.from("id\n1\n") },
    { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("id\n1\n") },
    { name: "third.csv", mimeType: "text/csv", buffer: Buffer.from("id\n3\n") },
  ]);
  await expect(page.locator(".file-name")).toHaveText(["first.csv", "third.csv"]);
  await expect(page.getByRole("alert")).toContainText("notes.txt");
  await expect(page.getByRole("main").getByRole("button", { name: "Check my files" })).toBeEnabled();
});

test("a failed delete says so", async ({ page }) => {
  await startWorkspace(page);
  await page.route("**/api/workspace", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ status: 500, contentType: "application/json", body: "{}" })
      : route.continue(),
  );
  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Delete my data" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Upload your files" })).toBeVisible();
});
