import { defineConfig } from "@playwright/test";

// Needs the full stack running: GigSim (:8001) + API serving the built UI (:8000), LLM_PROFILE=fake is fastest.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 180_000,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8000", trace: "retain-on-failure", screenshot: "only-on-failure" },
});
