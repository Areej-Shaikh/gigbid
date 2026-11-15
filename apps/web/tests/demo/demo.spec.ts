// One-off: screenshots of the main flow for the README demo GIF (not part of the e2e suite).
import { expect, test, type Page } from "@playwright/test";

const OUT = process.env.DEMO_OUT ?? "demo-frames";
let n = 0;
const shot = async (page: Page, name: string) => {
  n += 1;
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/${String(n).padStart(2, "0")}-${name}.png` });
};

async function openJob(page: Page, query: string, title: RegExp) {
  await page.getByRole("link", { name: "Inbox", exact: true }).click();
  await page.getByPlaceholder(/Search/).fill(query);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByText(title).first().click();
}

test("demo flow", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/login");
  await page.getByLabel("Username").fill(process.env.E2E_USER ?? "demo");
  await page.getByLabel("Password").fill(process.env.E2E_PASS ?? "demo123");
  await shot(page, "sign-in");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
  await shot(page, "inbox");

  // 1. one job from inbox to approved proposal
  await openJob(page, "ChatBot for support", /ChatBot for support with ChatGPT/);
  await page.getByRole("button", { name: "Analyse with agents" }).click();
  await page.waitForTimeout(2500);
  await shot(page, "agents-running");
  const studio = page.getByLabel("Proposal studio");
  await expect(studio).toBeVisible({ timeout: 120_000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await shot(page, "analysis");
  await studio.scrollIntoViewIfNeeded();
  await studio.locator(".cite").first().hover();
  await shot(page, "evidence-on-hover");
  await studio.getByText("Dry run:").scrollIntoViewIfNeeded();
  await shot(page, "dry-run-preview");
  await page.getByRole("button", { name: /Approve/ }).first().click();
  await page.waitForTimeout(3000);
  await shot(page, "approved");

  // 2. a scam caught
  await openJob(page, "pay outside platform", /Easy chatbot job, pay outside platform/);
  await page.getByRole("button", { name: "Analyse with agents" }).click();
  await expect(page.getByText(/Risk report/)).toBeVisible({ timeout: 60_000 });
  await page.getByText(/Risk report/).scrollIntoViewIfNeeded();
  await shot(page, "scam-skipped");

  // 3. an injected instruction flagged
  await page.goto("/jobs/job-01532");          // the planted copy; job-01295 is the clean original with the same title
  await page.getByRole("button", { name: "Analyse with agents" }).click();
  await expect(page.getByText(/Risk report/)).toBeVisible({ timeout: 60_000 });
  await page.getByText(/Risk report/).scrollIntoViewIfNeeded();
  await shot(page, "injection-flagged");

  // 4. client reply
  await page.getByRole("link", { name: "Messages" }).click();
  await page.waitForTimeout(1500);
  await shot(page, "messages");
});
