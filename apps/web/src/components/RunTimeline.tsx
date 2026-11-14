import { useEffect, useRef, useState } from "react";
import { auth, type TraceItem } from "../lib/api/client";

interface Ev { event: string; data: { node?: string; status?: string; trace?: TraceItem[]; message?: string } }

const NAMES: Record<string, string> = {
  intake: "Load job + client", analyst: "Job Analyst", risk: "Risk Assessor", fit: "Fit Matcher", decide: "Bid / skip decision",
  pricing: "Pricing Strategist", writer: "Proposal Writer", verifier: "Claim verification", critic: "Critic",
  compliance: "Compliance Guard", preview: "Dry-run preview", human_approval: "Your approval", submit: "Submit to marketplace",
  // conversation graph (Client Liaison)
  read_messages: "Read client messages", classify: "Classify intent", slots: "Find calendar slots",
  draft_reply: "Client Liaison draft", compliance_msg: "Compliance Guard", preview_msg: "Dry-run preview",
  approve_msg: "Your approval", send_msg: "Send to client",
};

function detail(t?: TraceItem): string {
  if (!t) return "";
  const skip = new Set(["node", "ts", "tokens", "error", "fallback_used"]);
  return Object.entries(t).filter(([k, v]) => !skip.has(k) && v !== null && v !== "" && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ");
}

// Live node-by-node progress from the API's Server-Sent Events stream.
export function RunTimeline({ jobId, active, onDone, eventsPath }: {
  jobId: string; active: number; onDone: () => void; eventsPath?: string;
}) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [live, setLive] = useState(false);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    if (!active) return;
    setEvents([]);
    setLive(true);
    const path = eventsPath ?? `/api/runs/${jobId}/events`;
    const es = new EventSource(`${path}?token=${encodeURIComponent(auth.get() ?? "")}`);
    const push = (event: string) => (m: MessageEvent) => setEvents((e) => [...e, { event, data: JSON.parse(m.data) }]);
    ["start", "node", "interrupt", "error"].forEach((n) => es.addEventListener(n, push(n)));
    es.addEventListener("done", (m) => { push("done")(m as MessageEvent); setLive(false); es.close(); done.current(); });
    es.onerror = () => { setLive(false); es.close(); done.current(); };
    return () => es.close();
  }, [jobId, active, eventsPath]);

  if (!active && !events.length) return null;
  return (
    <section className="card">
      <h3>Agent run {live && <span className="pulse" aria-label="running" />}</h3>
      <ol className="timeline">
        {events.filter((e) => e.event !== "start" && e.event !== "done").map((e, i) => {
          if (e.event === "error") return <li key={i} className="tl-error">Error: {e.data.message}</li>;
          if (e.event === "interrupt") return <li key={i} className="tl-wait">Paused: waiting for your approval</li>;
          const t = e.data.trace?.[e.data.trace.length - 1];
          return (
            <li key={i} className={t?.fallback_used === false ? "tl-llm" : ""}>
              <strong>{NAMES[e.data.node ?? ""] ?? e.data.node}</strong>
              {t?.model ? <span className="muted"> · {String(t.model)}{t.tokens ? ` · ${t.tokens} tok` : ""}</span> : null}
              <div className="muted small">{detail(t)}</div>
            </li>
          );
        })}
        {live && <li className="tl-live">working…</li>}
      </ol>
    </section>
  );
}
