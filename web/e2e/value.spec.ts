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
  const accuracy = page.locator("#accuracy");
  await expect(accuracy).toContainText("On questions it never saw");
  await expect(accuracy).toContainText("On questions it was tuned on");
  const [low, high] = holdout.wrong_answer_rate_given_answered.ci95;
  await expect(page.locator("#holdout-wrong")).toContainText(`95% range ${(low * 100).toFixed(1)}% to ${(high * 100).toFixed(1)}%`);
  await expect(page.locator("#seen-wrong")).toContainText(
    `${(seen.wrong_answer_rate_given_answered.rate * 100).toFixed(1)}%`,
  );

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
    answeredShare: holdout.coverage.rate,
  };
  await expect(page.locator("#out-net")).toHaveText(money(monthly(reader, measured).net));

  // Moving a slider changes the result.
  const before = await page.locator("#out-net").innerText();
  await page.locator("#questions-slider").fill("2000");
  await expect(page.locator("#questions-number")).toHaveValue("2000");
  await expect(page.locator("#out-net")).not.toHaveText(before);
  await expect(page.locator("#out-net")).toHaveText(money(monthly({ ...reader, questions: 2000 }, measured).net));
  const [atUnseen, atTuned] = range(
    { ...reader, questions: 2000 },
    { costPerQuestion: seen.mean_cost_usd, answeredShares: [holdout.coverage.rate, seen.coverage.rate] },
  );
  await expect(page.locator("#out-range-unseen")).toHaveText(money(atUnseen));
  await expect(page.locator("#out-range-tuned")).toHaveText(money(atTuned));

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

test("V3: the headline is the formula at the held-out answered share, and the range spans both shares", async ({ page }) => {
  await open(page);
  const reader = Object.fromEntries(INPUTS.map((s) => [s.key, s.example])) as unknown as Parameters<typeof monthly>[0];
  const out = monthly(reader, { costPerQuestion: seen.mean_cost_usd, answeredShare: holdout.coverage.rate });
  // Not the seen share: it is shown, but the headline must not use it.
  const atSeen = monthly(reader, { costPerQuestion: seen.mean_cost_usd, answeredShare: seen.coverage.rate });
  expect(money(atSeen.net)).not.toBe(money(out.net));
  await expect(page.locator("#out-net")).toHaveText(money(out.net));
  await expect(page.locator("#out-value-of-time")).toHaveText(money(out.valueOfTime));
  await expect(page.locator("#out-running-cost")).toHaveText(money(out.runningCost));

  await expect(page.locator("#out-range-unseen")).toHaveText(money(out.net));
  await expect(page.locator("#out-range-tuned")).toHaveText(money(atSeen.net));
  await expect(page.locator("#out-range")).toContainText("on questions it never saw");
  await expect(page.locator("#out-range")).toContainText("on questions it was tuned on");

  // The dollar-risk term is gone, and wrong-answer rates do not move the result.
  await expect(page.locator("#out-risk")).toHaveCount(0);
  await expect(page.locator("#inputs")).not.toContainText("wrong answer");
  await expect(page.locator("#accuracy")).toBeVisible();
  await expect(page.locator("#measured")).toContainText("These do not feed the formula.");
  await expect(page.locator("#measured")).toContainText("Every answer shows its query; the check time is counted.");
  await expect(page.locator("#measured")).toContainText("Model cost is the provider's list price.");
  await expect(page.locator("#app")).not.toContainText("credits");
});

test("at $0 findings every figure is unchanged; findings add to net value and clamp", async ({ page }) => {
  await open(page);
  await expect(page.locator("#findings-number")).toHaveValue("0");
  // The example figures before the findings input existed, pinned.
  await expect(page.locator("#out-net")).toHaveText("$5,775.47");
  await expect(page.locator("#out-range-unseen")).toHaveText("$5,775.47");
  await expect(page.locator("#out-range-tuned")).toHaveText("$7,873.48");
  await expect(page.locator("#out-running-cost")).toHaveText("$10.24");

  const box = page.locator("#findings-number");
  await box.fill("1000");
  await expect(page.locator("#out-findings")).toHaveText("$1,000.00");
  await expect(page.locator("#out-net")).toHaveText("$6,775.47");
  await expect(page.locator("#out-range-tuned")).toHaveText("$8,873.48");

  const spec = INPUTS.find((s) => s.key === "findings")!;
  await box.fill(String(spec.max * 10));
  await box.press("Tab");
  await expect(box).toHaveValue(String(spec.max));
  await box.fill("-5");
  await box.press("Tab");
  await expect(box).toHaveValue("0");
  await expect(page.locator("#out-net")).toHaveText("$5,775.47");
  await noBadNumbers(page);
});

test("the new lines: findings note, question example, and a measured answer time", async ({ page }) => {
  await open(page);
  const findings = page.locator(".value-input").filter({ has: page.locator("#findings-slider") });
  await expect(findings).toContainText("Savings from findings you'd act on each month (your estimate)");
  await expect(findings).toContainText(
    "Messy data hides costs no one has time to look for. When asking takes seconds, people ask the questions they used to skip.",
  );
  await expect(findings).toContainText("Example, replace with your own");

  const questions = page.locator(".value-input").filter({ has: page.locator("#questions-slider") });
  await expect(questions).toContainText("Data questions your team asks each month");
  await expect(questions).toContainText("e.g. 'How many deals closed last month?'");

  const seconds = (holdout.p50_latency_ms / 1000).toFixed(1);
  const answerTime = page.locator("#answer-time");
  await expect(answerTime).toHaveAttribute("data-source", SOURCE.holdout);
  await expect(answerTime).toContainText(
    `Answer time: about ${seconds} seconds, compared with hours or days in someone's queue.`,
  );
  await expect(answerTime).toContainText(`median over ${SOURCE.holdout}`);
  await expect(answerTime).not.toContainText("$");
});

test("V3: the page shows the formula", async ({ page }) => {
  await open(page);
  const formula = page.locator("#formula");
  await expect(formula).toContainText("running cost  = questions × cost per question + hosting");
  await expect(formula).toContainText("net value     = value of time + findings − running cost");
  await expect(formula).not.toContainText("risk");
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
  const table = page.locator("#measured");
  expect(await table.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await noBadNumbers(page);
});
