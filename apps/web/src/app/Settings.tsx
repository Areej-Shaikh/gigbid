import { Fragment, useEffect, useState } from "react";
import { api, errorText, type S } from "../lib/api/client";
import { ErrorBox, Loading } from "../components/ui";

export function Settings() {
  const [s, setS] = useState<S["Settings"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.GET("/api/settings").then(({ data, error }) => (error ? setError(errorText(error)) : setS(data!))); }, []);
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!s) return <Loading what="Loading settings" />;
  return (
    <>
      <h2>Settings</h2>
      <div className="grid2">
        <section className="card">
          <h3>Profile</h3>
          <dl className="kv">
            <dt>Signed in as</dt><dd>{s.username}</dd>
            <dt>Persona</dt><dd>{s.persona}</dd>
            <dt>Headline</dt><dd>{s.headline}</dd>
            <dt>Rate</dt><dd>${s.hourly_rate}/hr</dd>
            <dt>Skills</dt><dd className="row gap wrap">{s.skills.map((k) => <span key={k} className="chip">{k}</span>)}</dd>
          </dl>
        </section>
        <section className="card">
          <h3>Autonomy &amp; budgets</h3>
          <dl className="kv">
            <dt>Autonomy</dt><dd>Auto-skip low-fit and risky jobs; <strong>never auto-send</strong></dd>
            <dt>Min hourly</dt><dd>${String(s.user.min_hourly_rate)}</dd>
            <dt>Min fixed budget</dt><dd>${String(s.user.min_fixed_budget)}</dd>
            <dt>Weekly Connects</dt><dd>{String(s.user.weekly_connects_budget)}</dd>
            <dt>Bid if fit ≥</dt><dd>{String(s.decision.min_fit)}</dd>
            <dt>Max revisions</dt><dd>{String(s.budgets.max_revisions)}</dd>
            <dt>Token budget / job</dt><dd>{String(s.budgets.max_tokens_per_thread)}</dd>
          </dl>
          <p className="muted small">Edit these in agent/config.yaml (UI editing comes later).</p>
        </section>
        <section className="card">
          <h3>Models ({s.llm_profile} profile)</h3>
          <dl className="kv">{Object.entries(s.models).map(([n, m]) => <Fragment key={n}><dt>{n}</dt><dd className="mono">{m}</dd></Fragment>)}</dl>
        </section>
      </div>
      <MemoryViewer />
    </>
  );
}

// What GigBid has learned (R7): every item shows the promotion rule that let it in, and can be deleted.
function MemoryViewer() {
  const [m, setM] = useState<S["MemoryView"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = () => api.GET("/api/memory").then(({ data, error }) => (error ? setError(errorText(error)) : setM(data!)));
  useEffect(() => { load(); }, []);

  async function forget(kind: string, key: string) {
    const { data, error } = await api.DELETE("/api/memory/{kind}/{key}", { params: { path: { kind, key } } });
    if (error) return setError(errorText(error));
    setM(data!); setNote(`Deleted "${key}".`);
  }
  async function sync() {
    const { data, error } = await api.POST("/api/memory/sync-outcomes");
    if (error) return setError(errorText(error));
    setNote(`Checked ${data!.proposals} proposals, recorded ${data!.outcomes_recorded} outcomes` +
      (data!.categories_promoted.length ? `, promoted: ${data!.categories_promoted.join(", ")}.` : "."));
    load();
  }

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!m) return <Loading what="Loading memory" />;
  const rules = m.promotion_rules as { style: { promote_after_jobs: number }; outcome: { min_samples: number } };
  const need = rules.style.promote_after_jobs;
  return (
    <section className="card memory" aria-label="What GigBid has learned">
      <div className="row between wrap gap">
        <h3>What GigBid has learned</h3>
        <button className="btn" onClick={sync}>Sync outcomes from marketplace</button>
      </div>
      {note && <p className="muted small" role="status">{note}</p>}

      <h4>Style memory <span className="muted small">(from your edits; promoted after {need} different jobs)</span></h4>
      {!m.style.length && <p className="muted small">Nothing yet. Edit drafts and GigBid learns patterns you repeat.</p>}
      <ul className="mem">
        {m.style.map((i) => (
          <li key={i.key}>
            <span>{i.rule}<br /><span className="muted small">{i.promoted_by} · jobs: {i.jobs.join(", ")}</span></span>
            <button className="btn small-btn" onClick={() => forget("style", i.key)} aria-label={`Delete style rule ${i.key}`}>Delete</button>
          </li>
        ))}
      </ul>

      <h4>Outcome memory <span className="muted small">(per job category; promoted after {rules.outcome.min_samples} outcomes)</span></h4>
      {!m.outcome.length && <p className="muted small">Nothing yet. Outcomes appear after clients reply to (or ignore) your proposals.</p>}
      <ul className="mem">
        {m.outcome.map((i) => (
          <li key={i.key}>
            <span><strong>{i.category}</strong>: {i.positive}/{i.samples} got replies ({Math.round((i.reply_rate ?? 0) * 100)}%)
              {i.winning_evidence.length > 0 && <> · evidence that won: <span className="mono">{i.winning_evidence.join(", ")}</span></>}
              <br /><span className="muted small">{i.promoted_by}</span></span>
            <button className="btn small-btn" onClick={() => forget("outcome", i.key)} aria-label={`Delete outcome memory ${i.key}`}>Delete</button>
          </li>
        ))}
      </ul>

      {m.style_candidates.length > 0 && (
        <details>
          <summary>Patterns seen but not learned yet ({m.style_candidates.length})</summary>
          <ul className="mem">
            {m.style_candidates.map((i) => (
              <li key={i.key}>
                <span>{i.rule} <span className="muted small">· seen on {i.jobs.length}/{need} jobs</span></span>
                <button className="btn small-btn" onClick={() => forget("style_candidates", i.key)} aria-label={`Delete pattern ${i.key}`}>Delete</button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
