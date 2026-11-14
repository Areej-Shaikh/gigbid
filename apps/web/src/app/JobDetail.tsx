import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, errorText, type Evidence, type MatrixRow, type RunState } from "../lib/api/client";
import { ApprovalPanel } from "../components/ApprovalPanel";
import { RunTimeline } from "../components/RunTimeline";
import { EvidenceText } from "../components/EvidenceText";
import { Badge, ErrorBox, Loading, actionTone, label, money, riskTone, statusTone } from "../components/ui";

export function JobDetail() {
  const { id = "" } = useParams();
  const [run, setRun] = useState<RunState | null>(null);
  const [notRun, setNotRun] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);   // bump to (re)open the live stream

  const load = useCallback(async () => {
    const { data, error, response } = await api.GET("/api/runs/{job_id}", { params: { path: { job_id: id } } });
    if (response.status === 404) { setNotRun(true); return; }
    if (error) return setError(errorText(error));
    setNotRun(false); setRun(data!);
    if (data!.running) setActive((a) => a || 1);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function analyse() {
    setError(null);
    await api.POST("/api/runs/{job_id}", { params: { path: { job_id: id } } });
    setNotRun(false); setActive((a) => a + 1);
  }

  const v = (run?.values ?? {}) as Record<string, any>;
  const job = v.job ?? {};
  const evidence: Record<string, Evidence> = v.evidence ?? {};

  return (
    <>
      <Link to="/" className="muted small">← Inbox</Link>
      {error && <ErrorBox>{error}</ErrorBox>}
      {notRun && !active && (
        <section className="card">
          <h2>{id}</h2>
          <p className="muted">This job has not been analysed yet.</p>
          <button className="btn primary" onClick={analyse}>Analyse with agents</button>
        </section>
      )}
      {!run && !notRun && !error && <Loading what="Loading run" />}

      <div className="grid2">
        <div className="stack">
          {run && (
            <section className="card">
              <div className="row between wrap gap">
                <h2>{job.title}</h2>
                <Badge tone={statusTone(run.status)}>{label(run.status)}</Badge>
              </div>
              <p className="muted small">{money(job.budget_min, job.budget_type === "hourly")} – {money(job.budget_max, job.budget_type === "hourly")} · {job.budget_type} · {job.connects_cost} Connects · {job.job_id}</p>
              <p className="desc">{job.description || <em className="muted">No description.</em>}</p>
              {v.decision && (
                <div className="decision">
                  <Badge tone={actionTone(v.decision.action)}>{v.decision.action}</Badge>{" "}
                  <span>{v.decision.reasons.join(" · ")}</span>
                </div>
              )}
              {!!v.errors?.length && <ErrorBox>{v.errors.join("; ")}</ErrorBox>}
            </section>
          )}

          {v.job_spec && (
            <section className="card">
              <h3>JobSpec</h3>
              <dl className="kv">
                <dt>Requirements</dt><dd><ul>{v.job_spec.requirements.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></dd>
                {!!v.job_spec.deliverables?.length && <><dt>Deliverables</dt><dd><ul>{v.job_spec.deliverables.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></dd></>}
                {!!v.job_spec.hidden_needs?.length && <><dt>Hidden needs</dt><dd>{v.job_spec.hidden_needs.join(", ")}</dd></>}
                {!!job.screening_questions?.length && <><dt>Screening</dt><dd><ul>{job.screening_questions.map((q: string, i: number) => <li key={i}>{q}</li>)}</ul></dd></>}
              </dl>
            </section>
          )}

          {v.risk && (
            <section className="card">
              <h3>Risk report <Badge tone={riskTone(v.risk.level)}>{v.risk.level} · {v.risk.score}</Badge></h3>
              <p className="small muted">Client: {v.risk.client_summary}</p>
              {v.risk.reasons.length ? <ul>{v.risk.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul> : <p className="small">No warning signs.</p>}
            </section>
          )}

          {v.fit && (
            <section className="card">
              <h3>Requirement → evidence <Badge tone={v.fit.fit_score >= 0.5 ? "good" : "warn"}>fit {Math.round(v.fit.fit_score * 100)}%</Badge></h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Requirement</th><th>Proof from portfolio</th><th /></tr></thead>
                  <tbody>
                    {(v.fit.matrix as MatrixRow[]).map((r) => (
                      <tr key={r.requirement}>
                        <td>{r.requirement}</td>
                        <td className="small">{r.evidence_ids.map((e) => <div key={e} title={evidence[e]?.snippet}>{evidence[e]?.title ?? e}</div>)}</td>
                        <td>{r.covered ? <Badge tone="good">covered</Badge> : <Badge tone="bad">gap</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {v.price && (
            <section className="card">
              <h3>Price: {money(v.price.amount, v.price.budget_type === "hourly")}</h3>
              <ul className="small">{v.price.rationale.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
            </section>
          )}
        </div>

        <div className="stack">
          <RunTimeline jobId={id} active={active} onDone={load} />
          {run?.interrupt && !run.running && (
            <ApprovalPanel key={JSON.stringify(run.interrupt.draft)} jobId={id} payload={run.interrupt as any}
              questions={job.screening_questions ?? []} onSent={() => setActive((a) => a + 1)} />
          )}
          {v.submission && (
            <section className="card">
              <h3>Submitted <Badge tone="good">{v.submission.proposal_id}</Badge></h3>
              <p className="small">{v.submission.connects_cost} Connects spent, {v.submission.connects_balance_after} left.</p>
              {v.draft && <EvidenceText text={v.draft.cover_letter} evidence={evidence} />}
            </section>
          )}
          {run?.status === "rejected" && <section className="card"><h3>Rejected</h3><p>{v.approval?.reason}</p></section>}
          {run && !run.running && !run.interrupt && (
            <details className="card">
              <summary>Full trace ({(v.trace ?? []).length} steps, {v.tokens ?? 0} tokens)</summary>
              <pre className="trace">{JSON.stringify(v.trace, null, 1)}</pre>
            </details>
          )}
        </div>
      </div>
    </>
  );
}
