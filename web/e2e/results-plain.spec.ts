import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// The plain statement is read from the committed reports, so the expected figures are
// read from the same files here rather than typed in.
const REPORTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "evals", "reports");
const read = (id: string) => JSON.parse(fs.readFileSync(path.join(REPORTS, `${id}.json`), "utf-8"));

interface Rate {
  n: number;
  of: number;
  rate: number;
}
const now = read("v03-holdout");
const before = read("v03-holdout-before");
const askwell = (r: { table: { system: string }[] }) => r.table.find((t) => t.system === "ledgerline") as unknown as Record<string, Rate>;
const direct = now.table.find((t: { system: string }) => t.system === "oneshot") as Record<string, Rate>;
const right = (r: { question_level: { system: string; right: Rate }[] }, system: string) =>
  r.question_level.find((q) => q.system === system)!.right;
const oneIn = (r: Rate) => `1 in ${Math.round(r.of / r.n)}`;

test("the three plain answers render with the measured numbers", async ({ page }) => {
  await page.goto("/results/");
  const rightNow = right(now, "ledgerline");
  const wrong = askwell(now).wrong_answer_rate_given_answered;
  const refused = askwell(now).refusal_recall;
  expect(refused.n).toBe(refused.of);

  const rightLine = page.locator('.line[data-line="right"]');
  await expect(rightLine.locator(".figure strong")).toHaveText(`${rightNow.n} of ${rightNow.of}`);
  await expect(rightLine).toContainText(`up from ${right(before, "ledgerline").n} before v0.3`);
  // A question is a miss when it was missed in 2 or more of its 3 trials; of those, the
  // ones turned down in every trial.
  const outcomes = new Map<string, string[]>();
  for (const m of now.misses as { item_id: string; outcome: string }[])
    outcomes.set(m.item_id, [...(outcomes.get(m.item_id) ?? []), m.outcome]);
  const missed = [...outcomes.values()].filter((o) => o.length >= 2);
  expect(missed.length).toBe(rightNow.of - rightNow.n);
  const refusedAll = missed.filter((o) => o.length === 3 && o.every((x) => x === "refused")).length;
  await expect(rightLine.locator(".means")).toContainText(`(${refusedAll} of the ${missed.length} misses)`);
  await expect(rightLine.locator(".means")).toContainText("get the right answer");

  const wrongLine = page.locator('.line[data-line="wrong"]');
  await expect(wrongLine.locator(".figure strong")).toHaveText(`About ${oneIn(wrong)}`);
  await expect(wrongLine).toContainText(`down from ${oneIn(askwell(before).wrong_answer_rate_given_answered)} before v0.3`);

  const unsureLine = page.locator('.line[data-line="unsure"]');
  await expect(unsureLine.locator(".figure strong")).toHaveText(`All ${refused.of / now.trials}`);
  await expect(unsureLine).toContainText(`in all ${now.trials} runs`);
  await expect(unsureLine.locator(".means")).toContainText("private fields such as passwords");

  const compare = page.locator(".compare-ledger");
  await expect(compare).toContainText(`${right(now, "oneshot").n} of ${right(now, "oneshot").of}`);
  await expect(compare).toContainText(`About ${oneIn(direct.wrong_answer_rate_given_answered)}`);
  await expect(compare).toContainText(`(${(direct.wrong_answer_rate_given_answered.rate * 100).toFixed(1)}%)`);
});

test("the folds start closed and open and close from the keyboard", async ({ page }) => {
  await page.goto("/results/");
  const folds = page.locator("details.fold");
  await expect(folds).toHaveCount(3);
  for (const fold of await folds.all()) {
    await expect(fold).not.toHaveAttribute("open", /.*/);
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

test("the release check failure and the override are inside a fold, said plainly", async ({ page }) => {
  await page.goto("/results/");
  const fold = page.locator("#release-check");
  await fold.locator(":scope > summary").click();
  await expect(fold.locator('tr[data-schema="spider_world_1"][data-failed="true"]')).toHaveCount(2);
  await expect(fold).toContainText("The rule said not to ship.");
  await expect(fold).toContainText("approved the release anyway");
  await expect(fold.locator('a[href*="ADR-008"]')).toHaveCount(1);
});

test("no research term appears outside a fold", async ({ page }) => {
  const databases = new Set<string>();
  for (const f of fs.readdirSync(REPORTS).filter((f) => f.endsWith(".json"))) {
    for (const r of JSON.parse(fs.readFileSync(path.join(REPORTS, f), "utf-8")).table) {
      databases.add(r.schema);
      databases.add(r.schema.replace(/^spider_/, ""));
    }
  }
  const terms = [
    "execution accuracy",
    "refusal recall",
    "refusal",
    "one-shot",
    "baseline",
    "held-out",
    "held out",
    "spider",
    "triage",
    "intent",
    "registry",
    "ledgerline",
    ...databases,
  ];
  await page.goto("/results/");
  await expect(page.locator(".line")).toHaveCount(3);
  await expect(page.locator("details.fold")).toHaveCount(3);
  const outside = await page.evaluate(() => {
    const copy = document.body.cloneNode(true) as HTMLElement;
    copy.querySelectorAll("script, details > :not(summary)").forEach((el) => el.remove());
    return `${document.title} ${copy.textContent ?? ""}`.toLowerCase();
  });
  for (const term of terms) expect(outside, `"${term}" outside a fold`).not.toContain(term.toLowerCase());
});
