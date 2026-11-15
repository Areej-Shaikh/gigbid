import { defineConfig } from "@playwright/test";

// One-off: screenshots for the README demo GIF.  DEMO_OUT=<dir> npx playwright test --config playwright.demo.config.ts
export default defineConfig({
  testDir: "tests/demo",
  timeout: 240_000,
  workers: 1,
  use: { baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8000" },
});
