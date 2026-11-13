import { expect, type Page, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { INPUTS, monthly, range } from "../src/value-formula";
import { SOURCE } from "../src/value-source";

const REPORTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "evals", "reports");

function askwellRow(id: string) {
  const report = JSON.parse(fs.readFileSync(path.join(REPORTS, `${id}.json`), "utf-8"));
  return report.table.find((r: { system: string; model: string }) => r.system === "ledgerline" && r.model === SOURCE.model);
}

const seen = askwellRow(SOURCE.seen);
const holdout = askwellRow(SOURCE.holdout);

function money(value: number): string {
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${value < 0 ? "−" : ""}$${text}`;
}

async function open(page: Page): Promise<void> {
  await page.goto("/value/");
  await expect(page.locator("#results #out-net")).toBeVisible();
}

async function noBadNumbers(page: Page): Promise<void> {
  const text = await page.locator("#app").innerText();
  expect(text).not.toMatch(/NaN|Infinity/);
}

test("V1, V2: the page shows the model, run and cost from the committed reports", async ({ page }) => {
  await open(page);
  await expect(page.locator("#seen-model")).toHaveText(SOURCE.model);
  await expect(page.locator("#seen-run-id")).toHaveText(SOURCE.seen);
  await expect(page.locator("#seen-run-date")).toHaveText(SOURCE.date);
  await expect(page.locator("#holdout-run-id")).toHaveText(SOURCE.holdout);
  await expect(page.locator("#measured")).toContainText("measured on the seen questions");

  await expect(page.locator("#cost-per-question")).toHaveText(`$${seen.mean_cost_usd.toFixed(6)}`);
  await expect(page.locator("#seen-answered")).toContainText(`${(seen.coverage.rate * 100).toFixed(1)}%`);
  await expect(page.locator("#holdout-wrong")).toContainText(
    `${(holdout.wrong_answer_rate_given_answered.rate * 100).toFixed(1)}%`,
  );
});

test("V4: inputs are examples, measured figures name their source, and results follow the inputs", async ({ page }) => {
  await open(page);
  for (const spec of INPUTS) {
    const block = page.locator(".value-input").filter({ has: page.locator(`#${spec.key}-slider`) });
    await expect(block).toContainText("Example, replace with your own");
  }
  for (const id of ["cost-per-question", "seen-answered", "seen-wrong", "seen-run-id", "seen-model", "seen-run-date"]) {
    await expect(page.locator(`#${id}`)).toHaveAttribute("data-source", SOURCE.seen);
  }
  for (const id of ["holdout-answered", "holdout-wrong", "holdout-run-id"]) {
    await expect(page.locator(`#${id}`)).toHaveAttribute("data-source", SOURCE.holdout);
  }

  const reader = Object.fromEntries(INPUTS.map((s) => [s.key, s.example])) as unknown as Parameters<typeof monthly>[0];
  const measured = {
    costPerQuestion: seen.mean_cost_usd,
    answeredShare: seen.coverage.rate,
    wrongRate: seen.wrong_answer_rate_given_answered.rate,
  };
  await expect(page.locator("#out-net")).toHaveText(money(monthly(reader, measured).net));

  // Moving a slider changes the result.
  const before = await page.locator("#out-net").innerText();
  await page.locator("#questions-slider").fill("2000");
  await expect(page.locator("#questions-number")).toHaveValue("2000");
  await expect(page.locator("#out-net")).not.toHaveText(before);
  await expect(page.locator("#out-net")).toHaveText(money(monthly({ ...reader, questions: 2000 }, measured).net));
  const [atLow, atHigh] = range(
    { ...reader, questions: 2000 },
    {
      costPerQuestion: seen.mean_cost_usd,
      answeredShare: holdout.coverage.rate,
      wrongInterval: holdout.wrong_answer_rate_given_answered.ci95,
    },
  );
  await expect(page.locator("#out-range-low")).toHaveText(money(atLow));
  await expect(page.locator("#out-range-high")).toHaveText(money(atHigh));

  // Typing out of range clamps, in both directions, and nothing ever reads NaN or Infinity.
  const box = page.locator("#questions-number");
  await box.fill("99999999");
  await box.press("Tab");
  await expect(box).toHaveValue("10000");
  await expect(page.locator("#questions-slider")).toHaveValue("10000");
  await noBadNumbers(page);

  await box.fill("-40");
  await box.press("Tab");
  await expect(box).toHaveValue("0");
  await noBadNumbers(page);

  // The browser hands an overflowing number to the page as an empty value, so this and an
  // emptied box both fall back to the value in use.
  await box.fill("1e999");
  await box.press("Tab");
  await expect(box).toHaveValue("0");
  await noBadNumbers(page);

  await box.fill("");
  await box.press("Tab");
  await expect(box).toHaveValue("0");
  await noBadNumbers(page);
});

test("V3: the page shows the formula", async ({ page }) => {
  await open(page);
  const formula = page.locator("#formula");
  await expect(formula).toContainText("running cost  = questions × cost per question + hosting");
  await expect(formula).toContainText("net value     = value of time − risk − running cost");
  await expect(formula).toContainText("A refused question goes back to a person");
});

test("V6: keyboard alone, labelled inputs, reduced motion, no sideways scroll at 375 px", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 375, height: 800 });
  await open(page);

  const inputs = page.locator("#inputs input");
  await expect(inputs).toHaveCount(INPUTS.length * 2);
  for (const input of await inputs.all()) await expect(input).toHaveAccessibleName(/\S/);
  for (const spec of INPUTS) await expect(page.getByLabel(spec.label, { exact: false }).first()).toBeVisible();

  // Reach the first slider by Tab alone, then change it with the arrow keys.
  const slider = page.locator("#questions-slider");
  for (let i = 0; i < 20 && !(await slider.evaluate((el) => el === document.activeElement)); i++) {
    await page.keyboard.press("Tab");
  }
  await expect(slider).toBeFocused();
  const before = await page.locator("#out-net").innerText();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#questions-number")).toHaveValue("510");
  await expect(page.locator("#out-net")).not.toHaveText(before);

  await page.keyboard.press("Tab");
  await expect(page.locator("#questions-number")).toBeFocused();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("800");
  await expect(page.locator("#questions-slider")).toHaveValue("800");

  expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
  const table = page.locator("#measured .scroll");
  expect(await table.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await noBadNumbers(page);
});
