import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorText, type S } from "../lib/api/client";
import { ReplyPanel, type ReplyPayload } from "../components/ReplyPanel";
import { RunTimeline } from "../components/RunTimeline";
import { Badge, Empty, ErrorBox, Loading, label, statusTone } from "../components/ui";

export function Messages() {
  const [params, setParams] = useSearchParams();
  const [list, setList] = useState<S["ConversationSummary"][] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selected = params.get("c");

  const load = useCallback(() => {
    api.GET("/api/conversations").then(({ data, error }) => (error ? setError(errorText(error)) : setList(data!.conversations)));
  }, []);
  useEffect(load, [load]);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!list) return <Loading what="Loading messages" />;
  return (
    <>
      <h2>Messages</h2>
      <p className="muted small">Client replies appear here. The Client Liaison suggests a reply or interview slots; nothing is sent until you approve.</p>
      {!list.length && <Empty>No client messages yet. Clients reply after you submit proposals.</Empty>}
      <div className="conv">
        <nav className="conv-list" aria-label="Conversations">
          {list.map((c) => (
            <button key={c.client_id} className={`conv-item ${selected === c.client_id ? "active" : ""}`}
                    onClick={() => setParams({ c: c.client_id })}>
              <span className="row between gap">
                <strong>{c.client_id}</strong>
                {c.unanswered > 0 ? <Badge tone="info">{c.unanswered} new</Badge> : c.status ? <Badge tone={statusTone(c.status)}>{label(c.status)}</Badge> : null}
              </span>
              <span className="muted small">{c.last_sender === "freelancer" ? "You: " : ""}{c.last_text}</span>
            </button>
          ))}
        </nav>
        {selected ? <Thread key={selected} clientId={selected} onChange={load} /> : list.length > 0 && <Empty>Pick a conversation.</Empty>}
      </div>
    </>
  );
}

function Thread({ clientId, onChange }: { clientId: string; onChange: () => void }) {
  const [c, setC] = useState<S["ConversationState"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  const load = useCallback(() => {
    api.GET("/api/conversations/{client_id}", { params: { path: { client_id: clientId } } })
      .then(({ data, error }) => (error ? setError(errorText(error)) : setC(data!)));
  }, [clientId]);
  useEffect(load, [load]);

  async function suggest() {
    setError(null);
    const { error } = await api.POST("/api/conversations/{client_id}/run", { params: { path: { client_id: clientId } } });
    if (error) return setError(errorText(error));
    setActive((n) => n + 1);
  }
  const refresh = () => { load(); onChange(); };

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!c) return <Loading what="Loading conversation" />;
  const lastMine = c.messages.map((m) => m.sender).lastIndexOf("freelancer");
  const unanswered = c.messages.slice(lastMine + 1).some((m) => m.sender === "client");
  const v = c.values as { sent?: { hold?: { start: string } | null }; errors?: string[] };
  return (
    <section className="stack">
      <div className="card">
        <div className="row between wrap gap">
          <h3>{c.client_id}</h3>
          <Badge tone={statusTone(c.status)}>{label(c.status)}</Badge>
        </div>
        <div className="stack thread">
          {c.messages.map((m) => (
            <p key={m.message_id} className={m.sender === "client" ? "bubble" : "bubble me"}>
              <span className="muted small">{m.sender === "client" ? "Client" : "You"} · {new Date(m.sent_at).toLocaleString()}</span><br />{m.text}
            </p>
          ))}
        </div>
        {v.sent?.hold && <p className="muted small">Tentative interview hold on your calendar: {new Date(v.sent.hold.start).toLocaleString()}</p>}
        {!!v.errors?.length && c.status === "needs_attention" && <div className="state error" role="alert">{v.errors[v.errors.length - 1]}</div>}
        {!c.interrupt && !c.running && (
          <div className="row gap actions">
            <button className="btn primary" onClick={suggest} disabled={!unanswered}>Suggest a reply</button>
            {!unanswered && <span className="muted small">All client messages are answered.</span>}
          </div>
        )}
      </div>
      <RunTimeline jobId={clientId} active={active} onDone={refresh} eventsPath={`/api/conversations/${clientId}/events`} />
      {c.interrupt && !c.running && (
        <ReplyPanel key={JSON.stringify(c.interrupt.draft)} clientId={clientId} payload={c.interrupt as unknown as ReplyPayload}
                    onSent={() => setActive((n) => n + 1)} />
      )}
    </section>
  );
}
