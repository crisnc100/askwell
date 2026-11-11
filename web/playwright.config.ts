import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// The browser tests drive the built pages (npm run build) served by the real app, with
// a fake model that writes every request it gets to EXPORT_DIR (tests/e2e/serve.py).
const PORT = 8765;
export const EXPORT_DIR = path.resolve(HERE, ".e2e", "export");

export default defineConfig({
  testDir: "e2e",
  forbidOnly: true,
  retries: 0,
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${PORT}`, browserName: "chromium" },
  webServer: {
    command: `uv run python -m tests.e2e.serve --port ${PORT} --export-dir ${EXPORT_DIR}`,
    cwd: path.resolve(HERE, ".."),
    url: `http://127.0.0.1:${PORT}/api/limits`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
