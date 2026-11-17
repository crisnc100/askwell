import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", "demo-answers.json"), "utf-8")) as {
  examples: string[];
  answers: Record<string, unknown>;
};
const RECORDED = JSON.parse(fs.readFileSync(path.join(HERE, "..", "src", "recorded-answer.json"), "utf-8")) as {
  question: string;
};

async function open(page: Page): Promise<{ asks: number }> {
  const seen = { asks: 0 };
  await page.route("**/schemas/fieldservice/examples", (route) => route.fulfill({ json: FIXTURE.examples }));
  await page.route("**/ask", async (route) => {
    seen.asks += 1;
    const body = route.request().postDataJSON() as { question: string };
    const answer = FIXTURE.answers[body.question];
    await route.fulfill(answer ? { json: answer } : { status: 409, json: { detail: "no recorded model answer" } });
  });
  await page.goto("/");
  return seen;
}

test("the page opens on the first starter's recorded answer without asking the API", async ({ page }) => {
  const seen = await open(page);
  expect(RECORDED.question).toBe(FIXTURE.examples[0]);
  await expect(page.locator("#question")).toHaveValue(RECORDED.question);
  await expect(page.locator("#slip-no")).toHaveText("0001");
  await expect(page.locator("#form-lines")).toContainText("status = unpaid");
  await expect(page.locator("#check-text")).toContainText("Passed.");
  await expect(page.locator(".answer-rows tbody td")).toHaveText(["161"]);
  await expect(page.locator("#stamp")).toHaveClass(/is-down/);
  await expect(page.locator("#stamp .stamp-value")).toHaveText("161");
  await expect(page.locator("#rows-sent")).toHaveText("0");
  await page.waitForTimeout(300);
  expect(seen.asks).toBe(0);
});

test("the SQL reads with its values written in and no short aliases", async ({ page }) => {
  await open(page);
  const sql = page.locator("#sql");
  await expect(sql).toContainText("WHERE invoices.status = 'unpaid'");
  await expect(page.locator("#sql-note")).toBeVisible();
  for (const jargon of ["%(", "::", "t0", " AS t"]) await expect(sql).not.toContainText(jargon);

  await page.getByRole("button", { name: "More questions" }).click();
  await page.locator("#starters li button", { hasText: "Per month this year" }).click();
  await expect(page.locator(".step[data-step='rows']")).toHaveAttribute("data-filled", "true");
  await expect(sql).toContainText("work_orders.opened_at >= '2026-01-01 00:00:00'");
  for (const jargon of ["%(", "::TIMESTAMP", "t0."]) await expect(sql).not.toContainText(jargon);
});

test("three or four starters show, the refusal among them, and the rest unfold", async ({ page }) => {
  await open(page);
  const shown = page.locator("#starters > ul li button");
  const count = await shown.count();
  expect(count).toBeGreaterThanOrEqual(3);
  expect(count).toBeLessThanOrEqual(4);
  await expect(shown.filter({ hasText: "Delete all void invoices." })).toHaveCount(1);
  const more = page.getByRole("button", { name: "More questions" });
  await expect(more).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator("#more-starters")).toBeHidden();
  await more.click();
  await expect(page.locator("#more-starters li button")).toHaveCount(FIXTURE.examples.length - count);
  await expect(page.locator("#more-starters")).toBeVisible();
  await expect(page.getByRole("button", { name: "Fewer questions" })).toHaveAttribute("aria-expanded", "true");
});

test("the carbon opens on the tables the form named and folds the rest", async ({ page }) => {
  await open(page);
  await expect(page.locator("#carbon-tables [data-table]")).toHaveCount(1);
  await expect(page.locator("#carbon-tables [data-table='invoices']")).toBeVisible();
  await expect(page.locator("#carbon-hidden .is-hidden")).toHaveCount(2);
  await expect(page.locator("#carbon-hidden")).toBeVisible();
  const rest = page.locator("#carbon-rest");
  await expect(rest.locator("summary")).toHaveText("7 other tables: names only");
  await expect(rest.locator("[data-table='customers']")).toBeHidden();
  await rest.locator("summary").click();
  await expect(rest.locator("[data-table='customers']")).toBeVisible();
  await expect(rest.locator("[data-table]")).toHaveCount(7);
});

test("the method reads as what the AI does against what it never does", async ({ page }) => {
  await open(page);
  const ledger = page.locator(".how-ledger");
  await expect(ledger.locator("th")).toHaveText(["What the AI does", "What it never does"]);
  const never = ledger.locator("tbody td:nth-child(2)");
  await expect(never).toHaveCount(4);
  for (const line of ["Never sees a row", "Never writes SQL", "Never sees hidden columns", "Never guesses when unsure"]) {
    await expect(never.filter({ hasText: line })).toHaveCount(1);
  }
});

test("on a phone the stamp sits with the rows and the nav is one row", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await expect(page.locator(".stamp-rows")).toBeVisible();
  await expect(page.locator(".stamp-rows .stamp-value")).toHaveText("161");
  await expect(page.locator("#stamp")).toBeHidden();
  const tops = await page.locator(".topbar nav a").evaluateAll((links) => links.map((a) => Math.round(a.getBoundingClientRect().top)));
  expect(new Set(tops).size).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});

test("the three numbers sit in the carbon, inside the first 1440x900 view", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page);
  const numbers = page.locator(".carbon .ledger a");
  await expect(numbers).toHaveCount(3);
  await expect(page.locator(".ledger")).toHaveCount(1);
  for (const link of await numbers.all()) {
    const box = await link.boundingBox();
    expect(box).not.toBeNull();
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(900);
  }
});

test("the method says what the AI is shown beyond names", async ({ page }) => {
  await open(page);
  await expect(page.locator(".how-ledger tbody td:nth-child(1)")).toContainText([
    "Works only from what it is shown: table and column names, each column's type and short description, and category labels.",
  ]);
  await expect(page.locator(".how-ledger")).not.toContainText("Works only from the table and column names it is shown.");
});
