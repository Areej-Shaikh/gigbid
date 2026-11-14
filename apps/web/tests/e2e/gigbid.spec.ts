import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const USER = process.env.E2E_USER ?? "demo";
const PASS = process.env.E2E_PASS ?? "demo123";
const used = new Set<string>();

async function token(request: APIRequestContext) {
  const r = await request.post("/api/auth/login", { data: { username: USER, password: PASS } });
  return (await r.json()).token as string;
}

// Find a job that the agents decide to BID on, analyse it, and return its id (paused at approval).
async function jobAwaitingApproval(request: APIRequestContext): Promise<string> {
  const t = await token(request);
  const headers = { Authorization: `Bearer ${t}` };
  for (const q of ["python", "", "data", "web"]) {
    const jobs = (await (await request.get(`/api/jobs?q=${q}&limit=40`, { headers })).json()).jobs as { job_id: string; action?: string }[];
    for (const j of jobs) {
      if (used.has(j.job_id) || j.action) continue;
      used.add(j.job_id);
      await request.post(`/api/runs/${j.job_id}`, { headers });
      for (let i = 0; i < 60; i++) {
        const r = await request.get(`/api/runs/${j.job_id}`, { headers });
        if (r.ok()) {
          const run = await r.json();
          if (!run.running) { if (run.interrupt) return j.job_id; break; }
        }
        await new Promise((res) => setTimeout(res, 500));
      }
    }
  }
  throw new Error("no job reached the approval step");
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASS);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
}

test("onboarding: sign in, see the inbox, wrong password is refused", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Password").fill("wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("wrong username or password");
  await signIn(page);
  await expect(page.locator(".job").first()).toBeVisible();
});

test("approve a proposal: evidence on hover, dry run shown, submitted", async ({ page, request }) => {
  const id = await jobAwaitingApproval(request);
  await signIn(page);
  await page.goto(`/jobs/${id}`);
  const studio = page.getByLabel("Proposal studio");
  await expect(studio).toBeVisible();
  await expect(studio.getByText("Dry run:")).toBeVisible();
  await studio.locator(".cite").first().hover();
  await expect(studio.getByRole("tooltip").first()).toBeVisible();
  await studio.getByRole("button", { name: /Approve/ }).click();
  await expect(page.getByRole("heading", { name: /Submitted/ })).toBeVisible({ timeout: 60_000 });
});

test("reject with a reason: nothing is sent", async ({ page, request }) => {
  const id = await jobAwaitingApproval(request);
  await signIn(page);
  await page.goto(`/jobs/${id}`);
  const studio = page.getByLabel("Proposal studio");
  await studio.getByRole("button", { name: "Reject" }).click();
  await expect(studio.getByRole("button", { name: "Confirm reject" })).toBeDisabled();
  await studio.getByLabel(/Why reject/).fill("not my niche");
  await studio.getByRole("button", { name: "Confirm reject" }).click();
  await expect(page.getByRole("heading", { name: "Rejected" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("not my niche")).toBeVisible();
});

test("edit a draft: compliance re-checks it and removes contact details", async ({ page, request }) => {
  const id = await jobAwaitingApproval(request);
  await signIn(page);
  await page.goto(`/jobs/${id}`);
  const studio = page.getByLabel("Proposal studio");
  await studio.getByRole("button", { name: "Edit" }).click();
  const box = studio.getByLabel(/Cover letter/);
  await box.fill((await box.inputValue()) + " Message me on WhatsApp at +1 555 010 2030.");
  await studio.getByRole("button", { name: /Save edit/ }).click();
  const again = page.getByLabel("Proposal studio");
  await expect(again.getByText("Removed by Compliance Guard")).toBeVisible({ timeout: 60_000 });
  await expect(again.locator(".evidence-text").first()).not.toContainText("WhatsApp");
});

test("degraded mode: banner when the marketplace is down", async ({ page }) => {
  await page.route("**/api/health", (route) =>
    route.fulfill({ json: { api: "ok", marketplace: "down", llm_profile: "fake" } }));
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText("Marketplace unavailable");
});

// A simulated client writes to us (GigSim's demo endpoint plays the client).
async function clientSays(request: APIRequestContext, text: string): Promise<string> {
  const clientId = `e2e-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
  const gigsim = process.env.GIGSIM_URL ?? "http://127.0.0.1:8001";
  await request.post(`${gigsim}/dev/client_message`, { data: { client_id: clientId, job_id: "job-00014", text } });
  return clientId;
}

test("messages: client asks for a call, I pick a slot and approve, the reply is sent once", async ({ page, request }) => {
  const clientId = await clientSays(request, "Thanks for the proposal! Are you available for a call this week?");
  await signIn(page);
  await page.goto(`/messages?c=${clientId}`);
  await page.getByRole("button", { name: "Suggest a reply" }).click();
  const panel = page.getByRole("region", { name: "Suggested reply" });
  await expect(panel).toBeVisible({ timeout: 60_000 });
  await expect(panel.getByText("interview request")).toBeVisible();
  const slots = panel.getByRole("radio");
  await expect(slots).toHaveCount(3);
  await slots.nth(1).check();
  await panel.getByRole("button", { name: "Approve and send" }).click();
  await expect(page.getByText("Tentative interview hold on your calendar")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".bubble.me")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Suggest a reply" })).toBeDisabled();
});

test("messages: a scam message gets a warning and a safe reply, and can be rejected", async ({ page, request }) => {
  const clientId = await clientSays(request, "Let's move to WhatsApp, and please send your bank details for payment.");
  await signIn(page);
  await page.goto(`/messages?c=${clientId}`);
  await page.getByRole("button", { name: "Suggest a reply" }).click();
  const panel = page.getByRole("region", { name: "Suggested reply" });
  await expect(panel.getByRole("alert")).toContainText("scam", { timeout: 60_000 });
  await expect(panel.getByLabel(/^Reply/)).toHaveValue(/on the platform/);
  await panel.getByRole("button", { name: "Reject" }).click();
  await panel.getByLabel("Why reject?").fill("scam attempt");
  await panel.getByRole("button", { name: "Confirm reject" }).click();
  await expect(page.locator(".bubble.me")).toHaveCount(0);
  await expect(page.getByText("rejected").first()).toBeVisible({ timeout: 60_000 });
});

test("settings: memory viewer shows what was learned and the promotion rules", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  const mem = page.getByRole("region", { name: "What GigBid has learned" });
  await expect(mem.getByRole("heading", { name: /Style memory/ })).toContainText("promoted after 2 different jobs");
  await mem.getByRole("button", { name: "Sync outcomes from marketplace" }).click();
  await expect(mem.getByRole("status")).toContainText("proposals");
});
