import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { clamp, INPUTS, monthly, type ReaderInputs, range } from "../src/value-formula";
import { SOURCE } from "../src/value-source";

// Pure unit tests: they import the page's formula directly and never open a browser.
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const READER: ReaderInputs = {
  questions: 500,
  minutesByHand: 20,
  minutesToCheck: 2,
  costPerHour: 60,
  hosting: 10,
};

test("V3: the formula on known inputs", () => {
  const out = monthly(READER, { costPerQuestion: 0.001, answeredShare: 0.8 });
  // 500 × 0.001 + 10
  expect(out.runningCost).toBeCloseTo(10.5, 10);
  expect(out.answered).toBeCloseTo(400, 10);
  // 400 × 18 ÷ 60
  expect(out.hoursSaved).toBeCloseTo(120, 10);
  expect(out.valueOfTime).toBeCloseTo(7200, 10);
  expect(out.net).toBeCloseTo(7200 - 10.5, 10);
  // The owner removed the dollar-risk term (2026-11-13); it must not come back.
  expect(out).not.toHaveProperty("risk");
  expect(INPUTS.map((spec) => spec.key)).not.toContain("wrongCost");
});

test("V3: a zero answered share saves nothing, but still costs", () => {
  const out = monthly(READER, { costPerQuestion: 0.001, answeredShare: 0 });
  expect(out.answered).toBe(0);
  expect(out.hoursSaved).toBe(0);
  expect(out.valueOfTime).toBe(0);
  expect(out.net).toBeCloseTo(-10.5, 10);
});

test("V3: checking that takes longer than answering by hand loses time", () => {
  const out = monthly(
    { ...READER, minutesByHand: 5, minutesToCheck: 11 },
    { costPerQuestion: 0.001, answeredShare: 0.5 },
  );
  // 250 answered × (5 − 11) ÷ 60
  expect(out.hoursSaved).toBeCloseTo(-25, 10);
  expect(out.valueOfTime).toBeCloseTo(-1500, 10);
  expect(out.net).toBeCloseTo(-1500 - 10.5, 10);
});

test("V5: the range is the formula at the two answered shares", () => {
  const cost = 0.00048;
  const [atUnseen, atTuned] = range(READER, { costPerQuestion: cost, answeredShares: [0.643, 0.876] });
  expect(atUnseen).toBe(monthly(READER, { costPerQuestion: cost, answeredShare: 0.643 }).net);
  expect(atTuned).toBe(monthly(READER, { costPerQuestion: cost, answeredShare: 0.876 }).net);
  // When checking is quicker than answering by hand, answering more is worth more.
  expect(atTuned).toBeGreaterThan(atUnseen);
});

test("clamp keeps every value finite and inside its bounds", () => {
  expect(clamp(5, 0, 10)).toBe(5);
  expect(clamp(-3, 0, 10)).toBe(0);
  expect(clamp(99, 0, 10)).toBe(10);
  expect(clamp(Infinity, 0, 10)).toBe(10);
  expect(clamp(-Infinity, 0, 10)).toBe(0);
  for (const spec of INPUTS) {
    expect(spec.example).toBeGreaterThanOrEqual(spec.min);
    expect(spec.example).toBeLessThanOrEqual(spec.max);
  }
});

test("V2: the report constant names committed live reports with an Askwell row for the default model", () => {
  const config = fs.readFileSync(path.join(ROOT, "askwell", "config.py"), "utf-8");
  const defaultModel = /default_model: str \| None = "([^"]+)"/.exec(config)?.[1];
  expect(defaultModel).toBeTruthy();
  expect(SOURCE.model).toBe(defaultModel);
  for (const id of [SOURCE.seen, SOURCE.holdout]) {
    const file = path.join(ROOT, "evals", "reports", `${id}.json`);
    expect(fs.existsSync(file), file).toBe(true);
    const report = JSON.parse(fs.readFileSync(file, "utf-8"));
    expect(report.run_id).toBe(id);
    expect(report.simulation).toBeNull();
    expect(report.status).toBe("complete");
    const rows = report.table.filter(
      (r: { system: string; model: string }) => r.system === "ledgerline" && r.model === defaultModel,
    );
    expect(rows).toHaveLength(1);
    expect(typeof rows[0].mean_cost_usd).toBe("number");
  }
});
