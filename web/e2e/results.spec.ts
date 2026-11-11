import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// L25: the Results page renders every schema of every committed report, read here from
// the files themselves so a report the API failed to list would still be tested.
const REPORTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "evals", "reports");
const reports = fs
  .readdirSync(REPORTS)
  .filter((f) => f.endsWith(".json"))
  .sort()
  .map((f) => ({ id: f.replace(/\.json$/, ""), data: JSON.parse(fs.readFileSync(path.join(REPORTS, f), "utf-8")) }));

const LABELS = [
  "Execution accuracy",
  "Wrong answers among answered",
  "Coverage",
  "Accuracy when it answered",
  "False refusals",
  "Refusal recall",
  "Execution errors",
];

test("the results page renders every schema of every committed report", async ({ page, request }) => {
  expect(reports.length).toBeGreaterThan(0);
  // The page opens on the report with the most schemas, sim-1, where the fieldservice
  // floor is not met in v0.1.
  await page.goto("/results/");
  await expect(page.locator('section.schema[data-schema="fieldservice"] .floor')).toContainText("Floor not met in v0.1");
  await expect(page.getByRole("note")).toContainText("standing in for openai/gpt-oss-120b");

  for (const { id, data } of reports) {
    await page.goto(`/results/?report=${encodeURIComponent(id)}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Benchmark results: ${id}`);

    const banner = page.getByRole("note");
    if (data.simulation) {
      await expect(banner).toContainText("Simulated.");
      await expect(banner).toContainText(data.simulation);
    } else {
      await expect(banner).toHaveText("Measured with a real model.");
    }

    const definitions = page.locator("#definitions");
    for (const label of LABELS) await expect(definitions.getByText(label, { exact: false }).first()).toBeVisible();

    const schemas = [...new Set<string>(data.table.map((r: { schema: string }) => r.schema))];
    await expect(page.locator("section.schema")).toHaveCount(schemas.length);
    for (const schema of schemas) {
      const section = page.locator(`section.schema[data-schema="${schema}"]`);
      const rows = data.table.filter((r: { schema: string }) => r.schema === schema);
      await expect(section.locator("table.metrics tbody tr")).toHaveCount(rows.length);
      for (const row of rows) {
        const cells = section.locator(`tr[data-system="${row.system}"] td`);
        await expect(cells).toHaveCount(LABELS.length);
        const accuracy = row.execution_accuracy;
        await expect(cells.first()).toContainText(`${accuracy.n} of ${accuracy.of}`);
        if (accuracy.rate !== null) await expect(cells.first()).toContainText(`${(accuracy.rate * 100).toFixed(1)}%`);
      }
      for (const floor of data.floors.filter((f: { schema: string }) => f.schema === schema)) {
        const box = section.locator(".floor");
        await expect(box).toHaveAttribute("data-met", String(floor.met));
        await expect(box).toContainText(floor.met ? "Floor met" : "Floor not met");
      }
      const misses = data.misses.filter((m: { schema: string }) => m.schema === schema);
      if (misses.length) await expect(section.locator(".misses tbody tr")).toHaveCount(misses.length);

      const link = section.locator("a.triage");
      await expect(link).toHaveCount(1);
      const triage = await request.get((await link.getAttribute("href")) ?? "");
      expect(triage.status()).toBe(200);
      if (misses.length) expect(await triage.text()).toContain(misses[0].item_id);
    }
    await expect(page.locator("#app script, #app img")).toHaveCount(0);
  }
});

