import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const venvPython = [resolve(root, ".venv/bin/python"), resolve(root, ".venv/Scripts/python.exe")].find(existsSync);
const python = process.env.MM_PYTHON ?? venvPython ?? "python";
const port = Number(process.env.MM_E2E_PORT ?? 8799);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    ...devices["iPhone 13"],
    browserName: "chromium",
  },
  webServer: {
    // Fresh import of the fictional demo data into an isolated, git-ignored folder, then serve the built frontend.
    command: `"${python}" -m memory_museum demo --data-dir data/e2e --reset --port ${port}`,
    cwd: root,
    url: `http://127.0.0.1:${port}/api/health`,
    timeout: 180_000,
    reuseExistingServer: false,
  },
});
