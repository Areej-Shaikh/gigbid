import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RunSummary } from "../lib/api/client";
import { Empty, Loading, money } from "../components/ui";

const COLUMNS: [string, string[]][] = [
  ["Drafted (needs you)", ["awaiting_approval"]],
  ["Submitted", ["submitted"]],
  ["Viewed / Replied / Interview / Hired", ["viewed", "replied", "interview", "hired"]],
  ["Watching", ["watch"]],
  ["Skipped", ["skipped"]],
  ["Rejected / Lost", ["rejected", "lost"]],
  ["Needs attention", ["needs_attention", "dead_letter", "marketplace_unavailable", "error_retry"]],
];

export function Pipeline() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  useEffect(() => {
    const load = () => api.GET("/api/runs").then(({ data }) => setRuns(data?.runs ?? []));
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);
  if (!runs) return <Loading what="Loading pipeline" />;
  if (!runs.length) return <Empty>No runs yet. Analyse a job from the inbox.</Empty>;
  return (
    <>
      <h2>Pipeline</h2>
      <div className="kanban">
        {COLUMNS.map(([name, statuses]) => {
          const items = runs.filter((r) => statuses.includes(r.status));
          return (
            <section key={name} className="col" aria-label={name}>
              <h3>{name} <span className="muted">{items.length}</span></h3>
              {items.map((r) => (
                <Link key={r.job_id} to={`/jobs/${r.job_id}`} className="card kcard">
                  <strong>{r.title || r.job_id}</strong>
                  <span className="small muted">fit {r.fit != null ? Math.round(r.fit * 100) + "%" : "–"} · {money(r.price)}</span>
                </Link>
              ))}
            </section>
          );
        })}
      </div>
    </>
  );
}
