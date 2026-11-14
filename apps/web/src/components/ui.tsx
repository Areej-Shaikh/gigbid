import type { ReactNode } from "react";

export function Badge({ tone = "neutral", children }: { tone?: "good" | "warn" | "bad" | "info" | "neutral"; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export const riskTone = (r?: string | null) => (r === "high" ? "bad" : r === "medium" ? "warn" : r === "low" ? "good" : "neutral");
export const actionTone = (a?: string | null) => (a === "bid" ? "good" : a === "watch" ? "warn" : a === "skip" ? "bad" : "neutral");
export const statusTone = (s?: string | null) =>
  s === "submitted" ? "good" : s === "awaiting_approval" ? "info" : s === "rejected" || s === "skipped" ? "neutral"
    : s === "needs_attention" || s === "dead_letter" || s === "marketplace_unavailable" || s === "error_retry" ? "bad" : "warn";

export const label = (s?: string | null) => (s ? s.replace(/_/g, " ") : "");

export function Loading({ what = "Loading" }: { what?: string }) {
  return <div className="state" role="status"><span className="spinner" aria-hidden /> {what}…</div>;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="state empty">{children}</div>;
}
export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="state error" role="alert">{children}</div>;
}
export function money(n?: number | null, hourly?: boolean) {
  if (n == null) return "–";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}${hourly ? "/hr" : ""}`;
}
