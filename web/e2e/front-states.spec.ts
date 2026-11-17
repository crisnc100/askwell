import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = JSON.parse(fs.readFileSync(path.join(HERE, "fixtures", "demo-answers.json"), "utf-8")) as {
  examples: string[];
};
const RECORDED = JSON.parse(fs.readFileSync(path.join(HERE, "..", "src", "recorded-answer.json"), "utf-8")) as Record<
  string,
  unknown
>;

async function open(page: Page, reply: (question: string) => { status?: number; json: unknown }): Promise<void> {
  await page.route("**/schemas/fieldservice/examples", (route) => route.fulfill({ json: FIXTURE.examples }));
  await page.route("**/ask", async (route) => {
    const { question } = route.request().postDataJSON() as { question: string };
    await route.fulfill(reply(question));
  });
  await page.goto("/");
  // The recorded answer's stamp lands on a fixed 1.36s timer after load (4 steps of
  // 340ms), which a busy machine can push past the default 5s; the wait is longer, the
  // assertion the same.
  await expect(page.locator("#stamp")).toHaveClass(/is-down/, { timeout: 15_000 });
}

test("a failed ask after load leaves nothing of the earlier answer on the slip", async ({ page }) => {
  await open(page, () => ({ status: 409, json: { detail: "no recorded model answer" } }));
  await page.locator("#question").fill("How many parts are there?");
  await page.locator("#ask-button").click();
  await expect(page.locator("#slip-error")).toBeVisible();

  await expect(page.locator("#form-lines")).not.toContainText("invoices");
  await expect(page.locator("#form-lines")).not.toContainText("unpaid");
  await expect(page.locator("#form-lines dd")).toHaveText(["", "", ""]);
  await expect(page.locator("#check-text")).not.toContainText("Passed");
  await expect(page.locator("#sql")).toHaveText("");
  await expect(page.locator("#sql-note")).toBeHidden();
  await expect(page.locator("#rows")).toBeEmpty();
  await expect(page.locator(".rows-with-stamp")).toBeHidden();
  for (const stamp of await page.locator(".stamp").all()) {
    await expect(stamp).toBeEmpty();
    await expect(stamp).not.toHaveClass(/is-down/);
  }
  await expect(page.locator(".carbon .is-used")).toHaveCount(0);
  await expect(page.locator("#carbon-tables")).toHaveText("Waiting for the form.");
  await expect(page.locator(".slip")).not.toContainText("161");
});

test("the readable SQL never rewrites inside a value", async ({ page }) => {
  const value = "Garcia  Ltd t0.name";
  await open(page, (question) => ({
    json: {
      ...RECORDED,
      question,
      intent: { intent_type: "row_list", entity: "customers", select: ["name"] },
      sql: "SELECT t0.name AS name \nFROM customers AS t0 \nWHERE t0.name = %(param_1)s::VARCHAR",
      params: { param_1: value },
      columns: ["name"],
      rows: [[value]],
    },
  }));
  await page.locator("#question").fill("Which customer is Garcia Ltd?");
  await page.locator("#ask-button").click();
  await expect(page.locator(".step[data-step='sql']")).toHaveAttribute("data-filled", "true");
  const sql = (await page.locator("#sql").textContent()) ?? "";
  expect(sql).toContain(`WHERE customers.name = '${value}'`);
  expect(sql).toContain("SELECT customers.name AS name");
  expect(sql).not.toContain("::VARCHAR");
  expect(sql).not.toContain("customers.name'");
});

test("rows tied at the cutoff are named, as on /try/", async ({ page }) => {
  await open(page, (question) => ({ json: { ...RECORDED, question, tied_at_cutoff: true } }));
  await expect(page.locator(".tie-note")).toHaveCount(0);
  await page.locator("#ask-button").click();
  await expect(page.locator(".tie-note")).toHaveText("More rows tie with the last one shown.");
});

test("a workspace link opened in a tab already on the front page forwards to /try/", async ({ page }) => {
  const created = await page.request.post("/api/workspaces", { data: { time_zone: "UTC" } });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };
  await open(page, () => ({ json: RECORDED }));
  await page.evaluate((ws) => (location.hash = `#ws=${ws}`), id);
  await expect(page).toHaveURL(new RegExp(`/try/#ws=${id}$`));
  await expect(page.getByRole("heading", { name: "Upload your files" })).toBeVisible();
});
