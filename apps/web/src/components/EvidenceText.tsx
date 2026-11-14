import type { Evidence } from "../lib/api/client";

// Renders text where every [evidence_id] becomes a chip; hover/focus shows the evidence behind the claim.
export function EvidenceText({ text, evidence }: { text: string; evidence: Record<string, Evidence> }) {
  const parts = text.split(/(\[[A-Za-z0-9_\-]+\])/g);
  return (
    <p className="evidence-text">
      {parts.map((p, i) => {
        const m = p.match(/^\[([A-Za-z0-9_\-]+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const ev = evidence[m[1]];
        return (
          <span key={i} className={`cite ${ev ? "" : "cite-missing"}`} tabIndex={0} aria-label={`evidence ${m[1]}`}>
            {ev ? "evidence" : "missing evidence"}
            <span className="cite-pop" role="tooltip">
              <strong>{ev?.title ?? m[1]}</strong>
              <span className="mono">{m[1]}</span>
              {ev?.snippet && <span>{ev.snippet}</span>}
            </span>
          </span>
        );
      })}
    </p>
  );
}
