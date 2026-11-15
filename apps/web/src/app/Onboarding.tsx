import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth, errorText, type S } from "../lib/api/client";
import { Badge, ErrorBox, Loading } from "../components/ui";

const PERSONA_NAMES: Record<string, string> = {
  ai_ml_engineer: "AI / ML engineer", data_analyst: "Data analyst", fullstack_developer: "Full-stack web developer",
};

// Sign-in and onboarding: persona, marketplace connection, portfolio upload, rates and weekly Connects budget.
export function Onboarding() {
  const nav = useNavigate();
  const [p, setP] = useState<S["ProfileOut"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [upload, setUpload] = useState<string | null>(null);
  const [searches, setSearches] = useState("");

  useEffect(() => {
    api.GET("/api/profile").then(({ data, error }) => {
      if (error || !data) return setError(errorText(error));
      setP(data); setSearches(data.saved_searches.join(", "));
    });
  }, []);

  async function uploadFile(file: File) {
    setUpload(`Uploading ${file.name}…`);
    const form = new FormData();
    form.append("file", file);
    const r = await fetch("/api/profile/portfolio", { method: "POST", body: form, headers: { Authorization: `Bearer ${auth.get() ?? ""}` } });
    const body = await r.json().catch(() => ({}));
    setUpload(r.ok ? `Added to your portfolio: ${(body.evidence_ids as string[]).join(", ")}` : `Upload failed: ${body.detail ?? r.status}`);
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!p) return;
    setSaving(true); setError(null);
    const { data, error } = await api.PUT("/api/profile", {
      body: {
        persona: p.persona, min_hourly_rate: p.min_hourly_rate, min_fixed_budget: p.min_fixed_budget,
        weekly_connects_budget: p.weekly_connects_budget, onboarded: true,
        saved_searches: searches.split(",").map((s) => s.trim()).filter(Boolean),
      },
    });
    setSaving(false);
    if (error || !data) return setError(errorText(error));
    nav("/");
  }

  if (error && !p) return <ErrorBox>{error}</ErrorBox>;
  if (!p) return <Loading what="Loading your profile" />;
  const num = (v: string) => (v === "" ? 0 : Number(v));
  return (
    <form className="onboarding" onSubmit={save}>
      <h2>Set up GigBid</h2>
      <p className="muted">Four quick steps. You can change any of this later in Settings.</p>

      <section className="card">
        <h3>1. Whose portfolio?</h3>
        <p className="muted small">GigBid proves every claim in a proposal with evidence from this portfolio.</p>
        <div className="choices" role="radiogroup" aria-label="Persona">
          {p.personas.map((name) => (
            <label key={name} className={`choice ${p.persona === name ? "on" : ""}`}>
              <input type="radio" name="persona" value={name} checked={p.persona === name} onChange={() => setP({ ...p, persona: name })} />
              {PERSONA_NAMES[name] ?? name}
            </label>
          ))}
        </div>
      </section>

      <section className="card">
        <h3>2. Marketplace</h3>
        <div className="row gap wrap">
          <Badge tone="good">GigSim connected</Badge>
          <Badge tone={p.upwork_connected ? "good" : "neutral"}>Upwork {p.upwork_connected ? "connected" : "not connected"}</Badge>
        </div>
        <p className="muted small">
          Upwork uses its official MCP server with OAuth; your tokens are stored encrypted and every proposal is created as a
          draft you confirm on Upwork. Connect once with <code>python scripts/connect_upwork.py --user {p.username}</code>.
        </p>
      </section>

      <section className="card">
        <h3>3. Add your work</h3>
        <label className="lbl" htmlFor="portfolio-file">Upload a PDF CV or a Markdown case study (.md)</label>
        <input id="portfolio-file" type="file" accept=".pdf,.md" onChange={(e) => e.target.files?.[0] && uploadFile(e.target.files[0])} />
        {upload && <p className="small" role="status">{upload}</p>}
      </section>

      <section className="card">
        <h3>4. Rates, budget and searches</h3>
        <div className="grid2">
          <div>
            <label className="lbl" htmlFor="min-hourly">Minimum hourly rate (USD)</label>
            <input id="min-hourly" type="number" min={1} value={p.min_hourly_rate} onChange={(e) => setP({ ...p, min_hourly_rate: num(e.target.value) })} />
          </div>
          <div>
            <label className="lbl" htmlFor="min-fixed">Minimum fixed-price budget (USD)</label>
            <input id="min-fixed" type="number" min={1} value={p.min_fixed_budget} onChange={(e) => setP({ ...p, min_fixed_budget: num(e.target.value) })} />
          </div>
          <div>
            <label className="lbl" htmlFor="connects">Weekly Connects budget</label>
            <input id="connects" type="number" min={0} value={p.weekly_connects_budget} onChange={(e) => setP({ ...p, weekly_connects_budget: num(e.target.value) })} />
          </div>
          <div>
            <label className="lbl" htmlFor="searches">Saved searches (comma separated)</label>
            <input id="searches" value={searches} onChange={(e) => setSearches(e.target.value)} placeholder="LLM, chatbot, data pipeline" />
          </div>
        </div>
        <p className="muted small">GigBid never bids below your minimum rate and skips jobs whose Connects cost exceeds your weekly budget.</p>
      </section>

      {error && <ErrorBox>{error}</ErrorBox>}
      <button className="btn primary" disabled={saving}>{saving ? "Saving…" : "Save and go to my inbox"}</button>
    </form>
  );
}
