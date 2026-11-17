import { expect, type Page, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { INPUTS, monthly, type ReaderInputs } from "../src/value-formula";
import { SOURCE } from "../src/value-source";

// Expected figures are read from the same committed reports the page reads, never typed.
const REPORTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "evals", "reports");

function askwellRow(id: string) {
  const report = JSON.parse(fs.readFileSync(path.join(REPORTS, `${id}.json`), "utf-8"));
  return report.table.find((r: { system: string; model: string }) => r.system === "ledgerline" && r.model === SOURCE.model);
}

const seen = askwellRow(SOURCE.seen);
const holdout = askwellRow(SOURCE.holdout);
const measured = { costPerQuestion: seen.mean_cost_usd, answeredShare: holdout.coverage.rate };
const examples = Object.fromEntries(INPUTS.map((s) => [s.key, s.example])) as unknown as ReaderInputs;

function money(value: number): string {
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${value < 0 ? "−" : ""}$${text}`;
}

function hours(value: number): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: 1 });
}

async function open(page: Page): Promise<void> {
  await page.goto("/value/");
  await expect(page.locator("#results #out-net")).toBeVisible();
}

test("typing a new number in any form line updates every line of the statement", async ({ page }) => {
  await open(page);
  const before = monthly(examples, measured);
  await expect(page.locator("#out-hours-saved")).toHaveText(hours(before.hoursSaved));

  await page.locator("#minutesByHand-number").fill("45");
  await expect(page.locator("#minutesByHand-slider")).toHaveValue("45");
  const afterMinutes = monthly({ ...examples, minutesByHand: 45 }, measured);
  await expect(page.locator("#out-hours-saved")).toHaveText(hours(afterMinutes.hoursSaved));
  await expect(page.locator("#out-value-of-time")).toHaveText(money(afterMinutes.valueOfTime));
  await expect(page.locator("#out-net")).toHaveText(money(afterMinutes.net));
  expect(money(afterMinutes.net)).not.toBe(money(before.net));

  await page.locator("#hosting-number").fill("250");
  const afterHosting = monthly({ ...examples, minutesByHand: 45, hosting: 250 }, measured);
  await expect(page.locator("#out-running-cost")).toHaveText(money(afterHosting.runningCost));
  await expect(page.locator("#out-net")).toHaveText(money(afterHosting.net));
});

test("the stated rates beside the result are the ones the formula uses", async ({ page }) => {
  await open(page);
  const assumed = page.locator(".assumed");
  await expect(assumed).toBeVisible();
  await expect(assumed).toContainText(`$${seen.mean_cost_usd.toFixed(6)}`);
  await expect(assumed).toContainText(`${(holdout.coverage.rate * 100).toFixed(1)}%`);
});

test("the folds start closed and open and close from the keyboard", async ({ page }) => {
  await open(page);
  const folds = page.locator("details.fold");
  await expect(folds).toHaveCount(2);
  for (const fold of await folds.all()) {
    await expect(fold).not.toHaveAttribute("open", /.*/);
    await expect(fold.locator(".fold-def")).toBeHidden();
    const summary = fold.locator(":scope > summary");
    await summary.focus();
    await expect(summary).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(fold).toHaveAttribute("open", "");
    await expect(fold.locator(".fold-def")).toBeVisible();
    await page.keyboard.press("Space");
    await expect(fold).not.toHaveAttribute("open", /.*/);
  }
});

test("no research term or report name appears outside a fold", async ({ page }) => {
  const terms = [
    "held-out",
    "held out",
    "one-shot",
    "baseline",
    "refusal",
    "intent",
    "registry",
    "ledgerline",
    "fieldservice",
    "benchmark",
    "schema",
    "answered share",
    "95%",
    "interval",
    "median",
    SOURCE.seen,
    SOURCE.holdout,
    SOURCE.model,
  ];
  await open(page);
  await expect(page.locator("details.fold")).toHaveCount(2);
  const outside = await page.evaluate(() => {
    const copy = document.body.cloneNode(true) as HTMLElement;
    copy.querySelectorAll("script, details > :not(summary)").forEach((el) => el.remove());
    return `${document.title} ${copy.textContent ?? ""}`.toLowerCase();
  });
  for (const term of terms) expect(outside, `"${term}" outside a fold`).not.toContain(term.toLowerCase());
});

test("the nav matches Results, and at 390 px nothing scrolls sideways even with the folds open", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  const links = page.locator(".topbar nav a");
  await expect(links).toHaveText(["How it works", "Results", "Try your data"]);
  await expect(page.locator(".topbar nav a[aria-current]")).toHaveCount(0);
  for (const summary of await page.locator("details.fold > summary").all()) await summary.click();
  await expect(page.locator("details.fold[open]")).toHaveCount(2);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  for (const id of ["measured", "formula"]) {
    expect(await page.locator(`#${id}`).evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  }
});
