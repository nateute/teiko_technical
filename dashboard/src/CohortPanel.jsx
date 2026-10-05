import { useEffect, useState } from "react";

// Same colors as the boxplots so "yes"/"no" read consistently across the dashboard
const RESPONSE = {
  yes: { label: "Response (yes)", color: "#3b82f6" },
  no: { label: "No response (no)", color: "#f59e0b" },
};
const SEX = { M: "Male (M)", F: "Female (F)" };
const NEUTRAL = "#6b7fd7";
const UNKNOWN_COLOR = "#9ca3af";
const ORDER = { response: ["yes", "no"], sex: ["M", "F"] };

// Fixed order for response/sex; projects keep the server's order (largest first). Unknown always last.
function arrange(rows, category) {
  const pref = ORDER[category];
  const rank = (lvl) => (lvl === "Unknown" ? 2e6 : pref ? (pref.indexOf(lvl) >= 0 ? pref.indexOf(lvl) : 1e6) : 0);
  return rows.map((r, i) => ({ ...r, _i: i })).sort((a, b) => rank(a.level) - rank(b.level) || a._i - b._i);
}

function BarList({ title, rows, total, labelOf, colorOf }) {
  return (
    <div>
      <h3>{title}</h3>
      <div className="bars">
        {rows.map((r) => {
          const share = total ? (100 * r.n_subjects) / total : 0;
          return (
            <div className="bar-row" key={r.level} title={`${labelOf(r.level)}: ${r.n_subjects} subjects (${share.toFixed(1)}%)`}>
              <span className="bar-label">{labelOf(r.level)}</span>
              <span className="bar-track">
                <span className="bar-fill" style={{ display: "block", width: `${share}%`, background: colorOf(r.level) }} />
                <span className="bar-value">{r.n_subjects} · {share.toFixed(0)}%</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function CohortPanel() {
  const [data, setData] = useState(undefined); // undefined = loading, null = none
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/subset-analysis")
      .then(async (r) => {
        const b = await r.json();
        if (!r.ok) throw new Error(b?.error || r.statusText);
        return b;
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel cohort"><p className="error">{error}</p></section>;
  if (data === undefined) return <section className="panel cohort"><p className="muted">Loading cohort…</p></section>;
  if (data === null)
    return (
      <section className="panel cohort">
        <h2>Baseline cohort</h2>
        <p className="muted">No cohort counts found. Run <code>subset_analysis.py</code> on <code>cell-count.db</code> first.</p>
      </section>
    );

  const { counts, total } = data;
  return (
    <section className="panel cohort">
      <div className="cohort-head">
        <h2>Baseline cohort: {data.condition} · {data.sample_type} · {data.treatment}</h2>
        <div className="cohort-total">{total} <span>subjects</span></div>
      </div>
      <p className="muted small">
        time_from_treatment_start = {data.time_from_treatment_start} · run #{data.run_id} · {data.run_at.slice(0, 10)}
      </p>

      <div className="cohort-grid">
        <BarList title="Subjects by project" rows={arrange(counts.project, "project")} total={total}
                 labelOf={(l) => l} colorOf={(l) => (l === "Unknown" ? UNKNOWN_COLOR : NEUTRAL)} />
        <BarList title="Subjects by response" rows={arrange(counts.response, "response")} total={total}
                 labelOf={(l) => RESPONSE[l]?.label ?? l}
                 colorOf={(l) => RESPONSE[l]?.color ?? UNKNOWN_COLOR} />
        <BarList title="Subjects by sex" rows={arrange(counts.sex, "sex")} total={total}
                 labelOf={(l) => SEX[l] ?? l} colorOf={(l) => (l === "Unknown" ? UNKNOWN_COLOR : NEUTRAL)} />
      </div>
    </section>
  );
}