import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorText, type JobCard } from "../lib/api/client";
import { Badge, Empty, ErrorBox, Loading, actionTone, label, money, riskTone } from "../components/ui";

const FILTERS = ["all", "new", "bid", "watch", "skip"] as const;

export function Inbox() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [jobs, setJobs] = useState<JobCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const { data, error } = await api.GET("/api/jobs", { params: { query: { q: query, limit: 40 } } });
    if (error) return setError(errorText(error));
    setJobs(data!.jobs);
  }, [query]);

  useEffect(() => { setJobs(null); load(); }, [load]);

  async function analyse(id: string) {
    await api.POST("/api/runs/{job_id}", { params: { path: { job_id: id } } });
    setJobs((js) => js?.map((j) => (j.job_id === id ? { ...j, status: "running" } : j)) ?? null);
    setTimeout(load, 2500);
  }

  const shown = (jobs ?? []).filter((j) => filter === "all" || (filter === "new" ? !j.action : j.action === filter));

  return (
    <>
      <div className="row between wrap gap">
        <h2>Job inbox</h2>
        <form className="row gap" onSubmit={(e) => { e.preventDefault(); setQuery(q); }} role="search">
          <input aria-label="Search jobs" placeholder="Search e.g. python, power bi" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn">Search</button>
        </form>
      </div>
      <div className="tabs" role="tablist">
        {FILTERS.map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? "tab on" : "tab"} onClick={() => setFilter(f)}>{f}</button>
        ))}
      </div>
      {error && <ErrorBox>{error}</ErrorBox>}
      {!jobs && !error && <Loading what="Loading jobs" />}
      {jobs && !shown.length && <Empty>No jobs here. Try another search or filter.</Empty>}
      <ul className="jobs">
        {shown.map((j) => (
          <li key={j.job_id} className="card job">
            <div className="row between gap">
              <Link to={`/jobs/${j.job_id}`} className="job-title">{j.title}</Link>
              <span className="muted small nowrap">{money(j.budget_max ?? j.budget_min, j.budget_type === "hourly")} · {j.connects_cost} Connects</span>
            </div>
            <div className="row gap wrap small">
              {j.skills.slice(0, 5).map((s) => <span key={s} className="chip">{s}</span>)}
            </div>
            <div className="row between wrap gap">
              <div className="row gap wrap">
                {j.action ? <Badge tone={actionTone(j.action)}>{j.action}</Badge> : <Badge>not analysed</Badge>}
                {j.fit != null && <Badge tone={j.fit >= 0.5 ? "good" : "warn"}>fit {Math.round(j.fit * 100)}%</Badge>}
                {j.risk && <Badge tone={riskTone(j.risk)}>risk {j.risk}</Badge>}
                {j.risk_flags.filter((f) => f !== "no_client_history").slice(0, 2).map((f) => <Badge key={f} tone="bad">{label(f)}</Badge>)}
                {j.price != null && <span className="small">suggest {money(j.price, j.budget_type === "hourly")}</span>}
                {j.status && <span className="muted small">{label(j.status)}</span>}
              </div>
              {j.action ? <Link className="btn small" to={`/jobs/${j.job_id}`}>Open</Link>
                : <button className="btn small primary" disabled={j.status === "running"} onClick={() => analyse(j.job_id)}>{j.status === "running" ? "Analysing…" : "Analyse"}</button>}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
