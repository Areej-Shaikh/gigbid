import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth, errorText } from "../lib/api/client";

export function Login() {
  const nav = useNavigate();
  const [username, setU] = useState("demo");
  const [password, setP] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    const { data, error } = await api.POST("/api/auth/login", { body: { username, password } });
    setBusy(false);
    if (error || !data) return setError(errorText(error));
    auth.set(data.token);
    nav("/");
  }

  return (
    <main className="login">
      <form className="card" onSubmit={submit}>
        <h1>GigBid</h1>
        <p className="muted">Your freelance copilot. It finds jobs, checks them and drafts proposals. You approve every send.</p>
        <label className="lbl" htmlFor="u">Username</label>
        <input id="u" value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" />
        <label className="lbl" htmlFor="p">Password</label>
        <input id="p" type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" />
        {error && <div className="state error" role="alert">{error}</div>}
        <button className="btn primary full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </main>
  );
}
