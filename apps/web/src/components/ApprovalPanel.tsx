import { useState } from "react";
import { api, errorText, type Evidence } from "../lib/api/client";
import { EvidenceText } from "./EvidenceText";
import { Badge, money } from "./ui";

interface Payload {
  draft: { cover_letter: string; screening_answers: string[] };
  evidence: Record<string, Evidence>;
  price: { amount: number; budget_type: string; rationale: string[] };
  job: { screening_questions?: string[] } & Record<string, unknown>;
  verification?: { checks: { claim: string; status: string; note: string }[]; unsupported_before: number; removed: string[] };
  critique?: { approved: boolean; issues: string[] };
  compliance?: { passed: boolean; violations: string[] };
  dry_run?: { connects_cost: number; connects_balance_after: number; would_send?: Record<string, unknown> };
}

// Proposal studio: every claim shows its evidence on hover; approve, edit or reject with a reason.
export function ApprovalPanel({ jobId, payload, questions, onSent }: { jobId: string; payload: Payload; questions: string[]; onSent: () => void }) {
  const [text, setText] = useState(payload.draft.cover_letter);
  const [editing, setEditing] = useState(false);
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const v = payload.verification;

  async function send(action: "approve" | "edit" | "reject") {
    setBusy(true); setError(null);
    const { error } = await api.POST("/api/runs/{job_id}/resume", {
      params: { path: { job_id: jobId } },
      body: { action, cover_letter: action === "edit" ? text : undefined, reason: action === "reject" ? reason : undefined },
    });
    setBusy(false);
    if (error) return setError(errorText(error));
    setEditing(false); setRejecting(false);
    onSent();
  }

  return (
    <section className="card studio" aria-label="Proposal studio">
      <div className="row between">
        <h3>Proposal studio</h3>
        <Badge tone="info">waiting for you</Badge>
      </div>

      {editing ? (
        <>
          <label className="lbl" htmlFor="letter">Cover letter (keep the [evidence_id] markers on claims)</label>
          <textarea id="letter" value={text} onChange={(e) => setText(e.target.value)} rows={12} />
        </>
      ) : (
        <EvidenceText text={payload.draft.cover_letter} evidence={payload.evidence} />
      )}

      {payload.draft.screening_answers.map((a, i) => (
        <div key={i} className="qa">
          <div className="muted small">Q: {questions[i]}</div>
          <EvidenceText text={a} evidence={payload.evidence} />
        </div>
      ))}

      <div className="checks">
        <div><Badge tone={v && v.unsupported_before ? "warn" : "good"}>claims</Badge> {v?.checks.length ?? 0} checked, {v?.unsupported_before ?? 0} unsupported removed</div>
        <div><Badge tone={payload.critique?.approved ? "good" : "warn"}>critic</Badge> {payload.critique?.approved ? "approved" : payload.critique?.issues.join("; ")}</div>
        <div><Badge tone={payload.compliance?.passed ? "good" : "warn"}>compliance</Badge> {payload.compliance?.passed ? "no policy issues" : `${payload.compliance?.violations.length} removed`}</div>
      </div>
      {!!payload.compliance?.violations.length && (
        <details><summary>Removed by Compliance Guard</summary><ul>{payload.compliance.violations.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
      )}

      <div className="dryrun">
        <strong>Dry run:</strong> will send this proposal at <strong>{money(payload.price.amount, payload.price.budget_type === "hourly")}</strong>,
        costs <strong>{payload.dry_run?.connects_cost} Connects</strong> (balance after: {payload.dry_run?.connects_balance_after}).
      </div>

      {error && <div className="state error" role="alert">{error}</div>}
      {rejecting && (
        <div>
          <label className="lbl" htmlFor="reason">Why reject? (used for learning)</label>
          <input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. too far from my niche" />
        </div>
      )}
      <div className="row gap wrap">
        {editing ? (
          <>
            <button className="btn primary" disabled={busy} onClick={() => send("edit")}>Save edit &amp; re-check</button>
            <button className="btn" disabled={busy} onClick={() => { setEditing(false); setText(payload.draft.cover_letter); }}>Cancel</button>
          </>
        ) : rejecting ? (
          <>
            <button className="btn danger" disabled={busy || !reason.trim()} onClick={() => send("reject")}>Confirm reject</button>
            <button className="btn" disabled={busy} onClick={() => setRejecting(false)}>Cancel</button>
          </>
        ) : (
          <>
            <button className="btn primary" disabled={busy} onClick={() => send("approve")}>Approve &amp; send</button>
            <button className="btn" disabled={busy} onClick={() => setEditing(true)}>Edit</button>
            <button className="btn" disabled={busy} onClick={() => setRejecting(true)}>Reject</button>
          </>
        )}
      </div>
    </section>
  );
}
