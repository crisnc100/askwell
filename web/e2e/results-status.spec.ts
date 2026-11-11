import { expect, test } from "@playwright/test";

// A report with no simulation mark is a real-model measurement only once it is complete.
// An export run with no answers yet is "partial" and has no mark either.
const BASE = {
  simulation: null,
  notes: [],
  table: [],
  floors: [],
  misses: [],
  triage_files: [],
};

for (const status of ["partial", "aborted at budget"]) {
  test(`an unfinished report (${status}) never claims a real-model measurement`, async ({ page }) => {
    await page.route("**/api/reports", (route) =>
      route.fulfill({ json: [{ id: "run", simulation: null, schemas: [] }] }),
    );
    await page.route("**/api/reports/run", (route) => route.fulfill({ json: { ...BASE, run_id: "run", status } }));
    await page.goto("/results/");
    const banner = page.getByRole("note");
    await expect(banner).toContainText("Not measured");
    await expect(banner).toContainText(status);
    await expect(page.getByText("Measured with a real model")).toHaveCount(0);
  });
}

test("a complete report with no simulation mark says it was measured with a real model", async ({ page }) => {
  await page.route("**/api/reports", (route) =>
    route.fulfill({ json: [{ id: "run", simulation: null, schemas: [] }] }),
  );
  await page.route("**/api/reports/run", (route) =>
    route.fulfill({ json: { ...BASE, run_id: "run", status: "complete" } }),
  );
  await page.goto("/results/");
  await expect(page.getByRole("note")).toHaveText("Measured with a real model.");
  await expect(page.locator("#status")).toHaveText("Status: complete.");
});
