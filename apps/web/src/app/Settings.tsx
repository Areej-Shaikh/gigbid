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
        <section className="card">
          <h3>What GigBid has learned</h3>
          <p className="muted small">Style memory (from your edits) and outcome memory (what wins) will be listed here, and you can delete any item.</p>
        </section>
      </div>
    </>
  );
}
