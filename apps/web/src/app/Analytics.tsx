import { useEffect, useState } from "react";
import { api, type S } from "../lib/api/client";
import { Loading } from "../components/ui";

function Bars({ data }: { data: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(data));
  return (
    <div className="bars">
      {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([k, n]) => (
        <div key={k} className="bar-row"><span>{k.replace(/_/g, " ")}</span><span className="bar" style={{ width: `${(n / max) * 100}%` }} /><span>{n}</span></div>
      ))}
    </div>
  );
}

export function Analytics() {
  const [a, setA] = useState<S["Analytics"] | null>(null);
  useEffect(() => { api.GET("/api/analytics").then(({ data }) => setA(data ?? null)); }, []);
  if (!a) return <Loading what="Loading analytics" />;
  const tiles: [string, string | number][] = [
    ["Jobs analysed", a.analysed], ["Proposals sent", a.submitted], ["Connects spent", a.connects_spent],
    ["Avg tokens / job", a.avg_tokens_per_job], ["p50 latency", a.p50_latency_s != null ? `${a.p50_latency_s}s` : "–"],
    ["p95 latency", a.p95_latency_s != null ? `${a.p95_latency_s}s` : "–"],
  ];
  return (
    <>
      <h2>Analytics</h2>
      <div className="tiles">{tiles.map(([k, v]) => <div key={k} className="card tile"><span className="muted small">{k}</span><strong>{v}</strong></div>)}</div>
      <div className="grid2">
        <section className="card"><h3>Decisions</h3><Bars data={a.by_action} /></section>
        <section className="card"><h3>Status</h3><Bars data={a.by_status} /></section>
        <section className="card"><h3>Top skip reasons</h3>{a.top_skip_reasons.length ? <ol>{a.top_skip_reasons.map((r) => <li key={r}>{r}</li>)}</ol> : <p className="muted">None yet.</p>}</section>
        <section className="card"><h3>Top rejection reasons</h3>{a.top_reject_reasons.length ? <ol>{a.top_reject_reasons.map((r) => <li key={r}>{r}</li>)}</ol> : <p className="muted">None yet.</p>}</section>
      </div>
      <p className="muted small">Reply and hire rates by category appear once client replies flow in from the marketplace.</p>
    </>
  );
}
