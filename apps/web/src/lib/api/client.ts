// Typed API client. schema.d.ts is GENERATED from FastAPI's OpenAPI: run `npm run gen:api` (do not hand-edit).
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type S = components["schemas"];
export type JobCard = S["JobCard"];
export type RunState = S["RunState"];
export type RunSummary = S["RunSummary"];

const KEY = "gigbid.token";

// W3C trace context: a new trace per user action, continued by the API, the agents and every MCP server.
function hex(bytes: number): string {
  const a = new Uint8Array(bytes);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}
export function traceparent(): string {
  return `00-${hex(16)}-${hex(8)}-01`;
}
export const auth = {
  get(): string | null {
    try { return localStorage.getItem(KEY); } catch { return null; }
  },
  set(t: string | null) {
    try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* private mode */ }
  },
};

const withAuth: Middleware = {
  onRequest({ request }) {
    const t = auth.get();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    request.headers.set("traceparent", traceparent());   // the trace id starts here, in the browser (E3)
    return request;
  },
  async onResponse({ request, response }) {
    // 503 = marketplace busy (rate limit) or briefly down: retry reads with a growing delay. Writes are never
    // retried here (the server side already uses idempotency keys and the user can press the button again).
    let r = response;
    for (let i = 0; i < 6 && r.status === 503 && request.method === "GET"; i++) {
      await new Promise((res) => setTimeout(res, 3000 * (i + 1)));
      r = await fetch(request.url, { method: "GET", headers: request.headers });
    }
    if (r.status === 401 && !location.pathname.startsWith("/login")) {
      auth.set(null);
      location.href = "/login";
    }
    return r;
  },
};

export const api = createClient<paths>({ baseUrl: "" });
api.use(withAuth);

export function errorText(e: unknown): string {
  if (e && typeof e === "object" && "detail" in e) return String((e as { detail: unknown }).detail);
  return "Something went wrong";
}

// Shapes inside RunState.values (the graph state is a free-form dict on the API side)
export interface Evidence { evidence_id?: string; title?: string; snippet?: string; type?: string; project?: string }
export interface MatrixRow { requirement: string; evidence_ids: string[]; best_score: number; covered: boolean }
export interface TraceItem { node: string; ts: string; [k: string]: unknown }
