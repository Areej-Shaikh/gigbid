import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, auth, type S } from "../lib/api/client";

const LINKS = [["/", "Inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/analytics", "Analytics"], ["/settings", "Settings"]];

export function Layout() {
  const nav = useNavigate();
  const [health, setHealth] = useState<S["Health"] | null>(null);
  const [apiDown, setApiDown] = useState(false);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const { data } = await api.GET("/api/health");
        if (alive) { setHealth(data ?? null); setApiDown(!data); }
      } catch { if (alive) setApiDown(true); }
    };
    check();
    const id = setInterval(check, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="shell">
      <header className="top">
        <strong className="brand">GigBid</strong>
        <nav aria-label="Main">
          {LINKS.map(([to, name]) => <NavLink key={to} to={to} end={to === "/"}>{name}</NavLink>)}
        </nav>
        <div className="row gap">
          {health && <span className="muted small">LLM: {health.llm_profile}</span>}
          <button className="btn small" onClick={() => { auth.set(null); nav("/login"); }}>Sign out</button>
        </div>
      </header>
      {(apiDown || health?.marketplace === "down") && (
        <div className="banner" role="alert">
          {apiDown ? "The GigBid API is not reachable. Retrying…" :
            "Marketplace unavailable. You can still review saved runs; new analysis and sending are queued until it is back."}
        </div>
      )}
      <main className="content"><Outlet /></main>
    </div>
  );
}
