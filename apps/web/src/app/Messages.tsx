import { useEffect, useState } from "react";
import { api, errorText, type S } from "../lib/api/client";
import { Empty, ErrorBox, Loading } from "../components/ui";

export function Messages() {
  const [msgs, setMsgs] = useState<S["Message"][] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.GET("/api/messages").then(({ data, error }) => (error ? setError(errorText(error)) : setMsgs(data!.messages)));
  }, []);
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!msgs) return <Loading what="Loading messages" />;
  const threads = Object.entries(msgs.reduce<Record<string, S["Message"][]>>((a, m) => ((a[m.client_id] ??= []).push(m), a), {}));
  return (
    <>
      <h2>Messages</h2>
      <p className="muted small">Client replies appear here. Suggested replies and interview slots come from the Client Liaison (conversation graph), always with your approval.</p>
      {!threads.length && <Empty>No client messages yet.</Empty>}
      {threads.map(([client, ms]) => (
        <section key={client} className="card">
          <h3>{client}</h3>
          {ms.map((m) => <p key={m.message_id} className={m.sender === "client" ? "bubble" : "bubble me"}><span className="muted small">{m.sender} · {m.sent_at}</span><br />{m.text}</p>)}
        </section>
      ))}
    </>
  );
}
