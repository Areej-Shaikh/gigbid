import { useState } from "react";
import { api, errorText } from "../lib/api/client";
import { Badge, label } from "./ui";

export interface ReplyPayload {
  incoming: { text: string; sent_at: string };
  intent: { intent: string; summary?: string; reasons?: string[] };
  draft: { text: string };
  slots: { start: string; end: string }[];
  compliance?: { passed: boolean; violations: string[] };
  dry_run?: { would_send?: { text?: string } };
}

const intentTone = (i: string) => (i === "scam_signal" ? "bad" : i === "interview_request" ? "good" : i === "negotiation" ? "warn" : "info");
const nice = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

// Client Liaison approval: nothing is sent to the client until you approve here.
export function ReplyPanel({ clientId, payload, onSent }: { clientId: string; payload: ReplyPayload; onSent: () => void }) {
  const [text, setText] = useState(payload.draft.text);
  const [slot, setSlot] = useState(payload.slots[0]?.start ?? "");
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const edited = text.trim() !== payload.draft.text.trim();
  const scam = payload.intent.intent === "scam_signal";

  async function send(action: "approve" | "edit" | "reject") {
    setBusy(true); setError(null);
    const { error } = await api.POST("/api/conversations/{client_id}/resume", {
      params: { path: { client_id: clientId } },
      body: {
        action,
        text: action === "edit" ? text : undefined,
        slot: action === "approve" && payload.slots.length ? slot : undefined,
        reason: action === "reject" ? reason : undefined,
      },
    });
    setBusy(false);
    if (error) return setError(errorText(error));
    setRejecting(false);
    onSent();
  }

  return (
    <section className="card studio" aria-label="Suggested reply">
      <div className="row between wrap gap">
        <h3>Suggested reply</h3>
        <span className="row gap">
          <Badge tone={intentTone(payload.intent.intent)}>{label(payload.intent.intent)}</Badge>
          <Badge tone="info">waiting for you</Badge>
        </span>
      </div>
      {scam && (
        <div className="state error" role="alert">
          This message looks like a scam or an attempt to move you off the platform. GigBid drafted a safe reply that
          keeps everything on the platform. You can also reject and ignore it.
        </div>
      )}
      {payload.intent.summary && <p className="muted small">Client wants: {payload.intent.summary}</p>}

      <label className="lbl" htmlFor="reply">Reply (edit freely; edits are re-checked by Compliance and teach style memory)</label>
      <textarea id="reply" value={text} onChange={(e) => setText(e.target.value)} rows={6} />

      {payload.slots.length > 0 && (
        <fieldset className="slots">
          <legend className="lbl">Interview slot to hold on your calendar</legend>
          {payload.slots.map((s) => (
            <label key={s.start} className="row gap">
              <input type="radio" name="slot" value={s.start} checked={slot === s.start} onChange={() => setSlot(s.start)} style={{ width: "auto" }} />
              {nice(s.start)}
            </label>
          ))}
        </fieldset>
      )}

      <div className="checks">
        <div><Badge tone={payload.compliance?.passed ? "good" : "warn"}>compliance</Badge> {payload.compliance?.passed ? "no policy issues" : `${payload.compliance?.violations.length} removed`}</div>
      </div>
      {!!payload.compliance?.violations.length && (
        <details><summary>Removed by Compliance Guard</summary><ul>{payload.compliance.violations.map((x, i) => <li key={i}>{x}</li>)}</ul></details>
      )}
      <div className="dryrun"><strong>Dry run:</strong> this exact text goes to the client in the platform chat only after you approve.</div>

      {error && <div className="state error" role="alert">{error}</div>}
      {rejecting && (
        <div>
          <label className="lbl" htmlFor="reject-reason">Why reject?</label>
          <input id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. looks like a scam" />
        </div>
      )}
      <div className="row gap wrap actions">
        {edited ? (
          <button className="btn primary" disabled={busy} onClick={() => send("edit")}>Save edit and re-check</button>
        ) : (
          <button className="btn primary" disabled={busy} onClick={() => send("approve")}>Approve and send</button>
        )}
        {edited && <button className="btn" disabled={busy} onClick={() => setText(payload.draft.text)}>Undo edit</button>}
        {rejecting ? (
          <button className="btn danger" disabled={busy || !reason.trim()} onClick={() => send("reject")}>Confirm reject</button>
        ) : (
          <button className="btn" disabled={busy} onClick={() => setRejecting(true)}>Reject</button>
        )}
      </div>
    </section>
  );
}
