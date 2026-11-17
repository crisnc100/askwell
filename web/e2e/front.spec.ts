import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// The browser-test server has no demo database, so the demo routes answer with replies
// recorded from the real API in replay mode (fixtures/demo-answers.json).
const FIXTURE = JSON.parse(
  fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "demo-answers.json"), "utf-8"),
) as { examples: string[]; answers: Record<string, unknown> };

async function demo(page: Page): Promise<{ schema_id: string; question: string }[]> {
  const asked: { schema_id: string; question: string }[] = [];
  await page.route("**/schemas/fieldservice/examples", (route) => route.fulfill({ json: FIXTURE.examples }));
  await page.route("**/ask", async (route) => {
    const body = route.request().postDataJSON() as { schema_id: string; question: string };
    asked.push(body);
    const answer = FIXTURE.answers[body.question];
    await route.fulfill(answer ? { json: answer } : { status: 409, json: { detail: "no recorded model answer" } });
  });
  await page.goto("/");
  await expect(page.locator("#starters li button")).toHaveCount(FIXTURE.examples.length);
  return asked;
}

test("a starter question steps the slip through form, check and SQL to checked rows", async ({ page }) => {
  const asked = await demo(page);
  await page.locator("#starters button", { hasText: "How many invoices are still unpaid?" }).click();

  for (const step of ["form", "check", "sql", "rows"]) {
    await expect(page.locator(`.step[data-step="${step}"]`)).toHaveAttribute("data-filled", "true");
  }
  expect(asked).toEqual([{ schema_id: "fieldservice", question: "How many invoices are still unpaid?" }]);
  await expect(page.locator("#question")).toHaveValue("How many invoices are still unpaid?");
  const form = page.locator("#form-lines");
  await expect(form).toContainText("invoices");
  await expect(form).toContainText("status = unpaid");
  await expect(page.locator("#check-text")).toContainText("Passed.");
  await expect(page.locator("#sql")).toContainText("FROM invoices");
  await expect(page.locator(".answer-rows tbody td")).toHaveText(["161"]);
  await expect(page.locator("#stamp")).toHaveClass(/is-down/);
  await expect(page.locator("#stamp")).toContainText("Checked");
  await expect(page.locator("#slip-no")).toHaveText("0002");
});

test("the carbon copy shows names only, hidden columns, and 0 rows sent", async ({ page }) => {
  await demo(page);
  await page.locator("#ask-button").click();
  await expect(page.locator("#stamp")).toHaveClass(/is-down/);

  await expect(page.locator("#rows-sent")).toHaveText("0");
  const cells = page.locator(".carbon [data-column] .cell");
  expect(await cells.count()).toBeGreaterThan(40);
  for (const text of await cells.allTextContents()) expect(text).toBe("");
  // The answer's value is stamped on the carbon, never written into what the AI saw.
  await expect(page.locator("#carbon-tables")).not.toContainText("161");
  await expect(page.locator("#carbon-hidden .is-hidden")).toHaveText(["users.emailhidden", "users.password_hashhidden"]);
  await expect(page.locator('[data-column="invoices.status"]')).toHaveClass(/is-used/);
  await expect(page.locator('[data-column="customers.name"]')).not.toHaveClass(/is-used/);
});

test("a question it should refuse is stamped not answered, with no SQL", async ({ page }) => {
  await demo(page);
  await page.locator("#starters button", { hasText: "Delete all void invoices." }).click();
  await expect(page.locator("#stamp")).toContainText("Not answered");
  await expect(page.locator("#check-text")).toContainText("Not answered.");
  await expect(page.locator("#sql")).toHaveText("No SQL was written.");
  await expect(page.locator(".answer-rows")).toHaveCount(0);
});

test("a question with no recorded answer says so in plain words", async ({ page }) => {
  await demo(page);
  await page.locator("#question").fill("How many parts are there?");
  await page.locator("#ask-button").click();
  await expect(page.locator("#slip-error")).toContainText("no recorded answer");
  await expect(page.locator("#slip-error")).not.toContainText("replay");
});

test("the three measured numbers render and link to the results", async ({ page }) => {
  await demo(page);
  const links = page.locator(".ledger a");
  await expect(links).toHaveText([
    "Right on 62 of 96 questions it had never seen",
    "Wrong about 1 answer in 25, down from 1 in 14",
    "When it can't answer safely, it says so: it refused all 72 questions it should have",
  ]);
  for (const link of await links.all()) await expect(link).toHaveAttribute("href", "/results/");
});

test("the Try your data link opens the app at /try/", async ({ page }) => {
  await demo(page);
  await page.locator(".own").getByRole("link", { name: "Try your data" }).click();
  await expect(page).toHaveURL(/\/try\/$/);
  await expect(page.getByRole("heading", { name: "Prepare your data" })).toBeVisible();
});

test("a workspace link from before the move forwards to /try/", async ({ page }) => {
  const created = await page.request.post("/api/workspaces", { data: { time_zone: "UTC" } });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  await page.goto(`/#ws=${id}`);
  await expect(page).toHaveURL(new RegExp(`/try/#ws=${id}$`));
  await expect(page.getByRole("heading", { name: "Upload your files" })).toBeVisible();
});
