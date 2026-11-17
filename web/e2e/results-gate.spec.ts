import { expect, test } from "@playwright/test";

const GATE_REPORTS = ["v03-spider-new-before", "v03-spider-new-gated", "v03-csv-new-before", "v03-csv-new"];

test("when the gate reports fail to load, the fold says so and still shows the override", async ({ page }) => {
  for (const id of GATE_REPORTS) {
    await page.route(`**/api/reports/${id}`, (route) => route.fulfill({ status: 500, body: "boom" }));
  }
  await page.goto("/results/");
  const fold = page.locator("#release-check");
  await fold.locator(":scope > summary").click();

  const alert = fold.getByRole("alert");
  await expect(alert).toContainText("Couldn't load these reports");
  for (const id of GATE_REPORTS) await expect(alert).toContainText(id);
  await expect(alert).not.toContainText("Not among the committed reports");

  await expect(fold.locator("table.gate")).toHaveCount(0);
  const override = fold.locator(".notice.override");
  await expect(override).toBeVisible();
  await expect(override).toContainText("The rule said not to ship.");
  await expect(override).toContainText("approved the release anyway");
  await expect(override.locator('a[href$="ADR-008-accuracy-v03.md"]')).toBeVisible();
});

test("a gate report missing from the list is named as missing, not as a load failure", async ({ page }) => {
  await page.route("**/api/reports", async (route) => {
    const listed = (await (await route.fetch()).json()) as { id: string }[];
    await route.fulfill({ json: listed.filter((r) => r.id !== "v03-csv-new") });
  });
  await page.goto("/results/");
  const fold = page.locator("#release-check");
  await fold.locator(":scope > summary").click();
  const alert = fold.getByRole("alert");
  await expect(alert).toHaveText("Not among the committed reports: v03-csv-new.");
  await expect(fold.locator('table.gate tr[data-schema="spider_world_1"][data-failed="true"]')).toHaveCount(1);
  await expect(fold.locator(".notice.override")).toContainText("The rule said not to ship.");
});

test("when every gate report loads, the fold shows no load notice", async ({ page }) => {
  await page.goto("/results/");
  const fold = page.locator("#release-check");
  await fold.locator(":scope > summary").click();
  await expect(fold.locator('tr[data-schema="spider_world_1"][data-failed="true"]')).toHaveCount(2);
  await expect(fold.getByRole("alert")).toHaveCount(0);
});
