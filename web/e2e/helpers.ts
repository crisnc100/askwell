import { expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { EXPORT_DIR } from "../playwright.config";

export const SAMPLE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "public", "sample");

export async function startWorkspace(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Prepare your data" })).toBeVisible();
  await expect(page.locator("#time-zone option")).not.toHaveCount(0);
  await page.getByRole("button", { name: "Start a workspace" }).click();
  await expect(page.getByRole("heading", { name: "Upload your files" })).toBeVisible();
}

// The newest request the fake model received, as the model saw it.
export function lastExportedRequest(): { messages: { role: string; content: string }[] } {
  const files = fs.readdirSync(EXPORT_DIR).filter((f) => f.endsWith(".json")).sort();
  if (!files.length) throw new Error("the fake model received no request");
  return JSON.parse(fs.readFileSync(path.join(EXPORT_DIR, files[files.length - 1]), "utf-8"));
}
