// Typed API client. schema.d.ts is GENERATED from FastAPI's OpenAPI: run `npm run gen:api` (do not hand-edit).
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type S = components["schemas"];
export type JobCard = S["JobCard"];
export type RunState = S["RunState"];
export type RunSummary = S["RunSummary"];

const KEY = "gigbid.token";
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
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && !location.pathname.startsWith("/login")) {
      auth.set(null);
      location.href = "/login";
    }
    return response;
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
