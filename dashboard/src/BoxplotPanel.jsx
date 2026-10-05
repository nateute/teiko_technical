import { useEffect, useState } from "react";

const POP_LABELS = {
  b_cell: "B cell",
  cd8_t_cell: "CD8+ T cell",
  cd4_t_cell: "CD4+ T cell",
  nk_cell: "NK cell",
  monocyte: "Monocyte",
};
const GROUPS = [
  { key: "yes", label: "Response", color: "#3b82f6" },
  { key: "no", label: "No response", color: "#f59e0b" },
];
const TESTS = { welch: "Welch's t-test", mwu: "Mann-Whitney U" };

// SVG geometry
const W = 520, H = 450;
const M = { top: 92, right: 24, bottom: 70, left: 62 };

function niceTicks(lo, hi, target = 6) {
  const range = hi - lo || 1;
  const rough = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toFixed(10)));
  return { ticks, decimals: Math.max(0, -Math.floor(Math.log10(step))) };
}

// Deterministic jitter in [-0.5, 0.5) so points don't move between renders
const jitter = (i, seed) => {
  const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x) - 0.5;
};

const fmt = (x, d = 3) => (x == null ? "NA" : Number(x).toFixed(d));
const pText = (p) => (p == null ? "adj. p = NA" : p < 0.0001 ? "adj. p < 0.0001" : `adj. p = ${p.toFixed(4)}`);
const stars = (p, significant) => {
  if (!significant) return "ns";
  if (p != null && p < 0.001) return "***";
  if (p != null && p < 0.01) return "**";
  return "*";
};

function timeLabel(notes = "") {
  const m = notes.match(/time_from_treatment_start = ([\d.]+)/);
  if (m) return `time = ${m[1]}`;
  return notes.includes("All timepoints pooled") ? "all timepoints pooled" : "";
}

/** One boxplot (Response vs No response) for a single population row. */
export function Boxplot({ row, test, showPoints }) {
  const all = [...row.values_yes, ...row.values_no];
  if (!all.length) return <p className="muted">No data for this population.</p>;

  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.08 || 1;
  const { ticks, decimals } = niceTicks(Math.max(0, lo - pad), hi + pad);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const y = (v) => M.top + plotH - ((v - y0) / (y1 - y0)) * plotH;
  const cx = [M.left + plotW * 0.27, M.left + plotW * 0.73];
  const boxW = 96;

  const p = row[`${test}_p_adjusted`];
  const significant = row[`${test}_significant`] === 1;
  const bracketY = M.top - 16; // fixed band above the plot so it never collides with data or gridlines

  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" role="img"
         aria-label={`Boxplot of ${POP_LABELS[row.population] ?? row.population}: response vs no response`}
         style={{ color: "currentColor", display: "block" }}>
      {/* y axis: grid, ticks, label */}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="currentColor" opacity="0.15" />
          <text x={M.left - 8} y={y(t) + 4} textAnchor="end" fontSize="12" fill="currentColor" opacity="0.7">
            {t.toFixed(decimals)}
          </text>
        </g>
      ))}
      <line x1={M.left} x2={M.left} y1={M.top} y2={M.top + plotH} stroke="currentColor" opacity="0.5" />
      <text transform={`translate(15 ${M.top + plotH / 2}) rotate(-90)`} textAnchor="middle" fontSize="13" fill="currentColor">
        Relative frequency (% of cells)
      </text>

      {/* boxes */}
      {GROUPS.map((g, gi) => {
        const n = row[`n_${g.key}`];
        if (!n) return null;
        const q1 = row[`q1_${g.key}`], q3 = row[`q3_${g.key}`], med = row[`median_${g.key}`];
        const wl = row[`whisker_low_${g.key}`], wh = row[`whisker_high_${g.key}`];
        const vals = row[`values_${g.key}`], outs = new Set(row[`outliers_${g.key}`]);
        const x = cx[gi];
        return (
          <g key={g.key}>
            <line x1={x} x2={x} y1={y(wh)} y2={y(q3)} stroke={g.color} strokeWidth="1.5" />
            <line x1={x} x2={x} y1={y(q1)} y2={y(wl)} stroke={g.color} strokeWidth="1.5" />
            <line x1={x - boxW * 0.2} x2={x + boxW * 0.2} y1={y(wh)} y2={y(wh)} stroke={g.color} strokeWidth="1.5" />
            <line x1={x - boxW * 0.2} x2={x + boxW * 0.2} y1={y(wl)} y2={y(wl)} stroke={g.color} strokeWidth="1.5" />
            <rect x={x - boxW / 2} y={y(q3)} width={boxW} height={Math.max(y(q1) - y(q3), 1)}
                  fill={g.color} fillOpacity="0.25" stroke={g.color} strokeWidth="1.5" />
            <line x1={x - boxW / 2} x2={x + boxW / 2} y1={y(med)} y2={y(med)} stroke={g.color} strokeWidth="3" />
            {showPoints
              ? vals.map((v, i) => (
                  <circle key={i} cx={x + jitter(i, gi + 1) * boxW * 0.7} cy={y(v)} r="3.2"
                          fill={outs.has(v) ? "none" : g.color} fillOpacity={outs.has(v) ? 1 : 0.7}
                          stroke={g.color} strokeWidth="1.3" />
                ))
              : [...outs].map((v, i) => (
                  <circle key={i} cx={x} cy={y(v)} r="3.5" fill="none" stroke={g.color} strokeWidth="1.5" />
                ))}
            <text x={x} y={H - M.bottom + 26} textAnchor="middle" fontSize="14" fontWeight="600" fill="currentColor">
              {g.label}
            </text>
            <text x={x} y={H - M.bottom + 44} textAnchor="middle" fontSize="12" fill="currentColor" opacity="0.7">
              n = {n}
            </text>
          </g>
        );
      })}

      {/* significance bracket: p-value on top, asterisks (or "ns") on the bracket */}
      <path d={`M${cx[0]},${bracketY + 10} V${bracketY} H${cx[1]} V${bracketY + 10}`}
            fill="none" stroke="currentColor" strokeWidth="1.5" />
      <text x={(cx[0] + cx[1]) / 2} y={bracketY - 3} textAnchor="middle"
            fontSize={significant ? 22 : 13} fontWeight="700" fill="currentColor">
        {stars(p, significant)}
      </text>
      <text x={(cx[0] + cx[1]) / 2} y={bracketY - 28} textAnchor="middle" fontSize="13" fill="currentColor">
        {pText(p)}
      </text>
    </svg>
  );
}

export default function BoxplotPanel() {
  const [analyses, setAnalyses] = useState(null);
  const [analysisId, setAnalysisId] = useState(null);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const [idx, setIdx] = useState(0);          // selected population
  const [test, setTest] = useState("welch");
  const [showPoints, setShowPoints] = useState(false);

  useEffect(() => {
    fetch("/api/analyses")
      .then(async (r) => {
        const b = await r.json();
        if (!r.ok) throw new Error(b.error || r.statusText);
        return b;
      })
      .then((a) => {
        setAnalyses(a);
        if (a.length) setAnalysisId(a[0].analysis_id); // newest run
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (analysisId == null) return;
    let cancelled = false;
    fetch(`/api/analyses/${analysisId}/results`)
      .then(async (r) => {
        const b = await r.json();
        if (!r.ok) throw new Error(b.error || r.statusText);
        return b;
      })
      .then((rows) => { if (!cancelled) { setResults(rows); setIdx(0); } })
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [analysisId]);

  if (error) return <section className="panel"><p className="error">{error}</p></section>;
  if (analyses === null) return <section className="panel"><p className="muted">Loading analyses…</p></section>;
  if (analyses.length === 0)
    return (
      <section className="panel">
        <h2>Response analysis</h2>
        <p className="muted">No analyses found. Run <code>response_analysis.py</code> on <code>cell-count.db</code> first.</p>
      </section>
    );

  const analysis = analyses.find((a) => a.analysis_id === analysisId) ?? analyses[0];
  const row = results[idx];
  const ciPct = Math.round((1 - analysis.alpha) * 100);
  const tl = timeLabel(analysis.notes);

  return (
    <section className="panel">
      {/* 1. run selector */}
      <select className="full" aria-label="Analysis run" value={analysisId ?? ""}
              onChange={(e) => setAnalysisId(Number(e.target.value))}>
        {analyses.map((a) => (
          <option key={a.analysis_id} value={a.analysis_id}>
            #{a.analysis_id} · {a.treatment} · {a.condition ?? "condition n/a"} · {a.sample_type} · {a.run_at.slice(0, 10)}
          </option>
        ))}
      </select>

      {/* 2. cell population selector (directly beneath the run selector) + test toggle */}
      <div className="panel-row">
        <select aria-label="Cell population" value={idx} onChange={(e) => setIdx(Number(e.target.value))}>
          {results.map((r, i) => (
            <option key={r.population} value={i}>{POP_LABELS[r.population] ?? r.population}</option>
          ))}
        </select>
        <div className="seg" role="group" aria-label="Statistical test">
          {Object.entries(TESTS).map(([k, label]) => (
            <button key={k} className={test === k ? "on" : ""} onClick={() => setTest(k)}>{label}</button>
          ))}
        </div>
      </div>

      {row && (
        <>
          <h2>{POP_LABELS[row.population] ?? row.population}: response vs. no response</h2>
          <p className="muted small">
            {analysis.treatment} · {analysis.condition ?? "condition n/a"} · {analysis.sample_type}
            {tl ? ` · ${tl}` : ""} · {analysis.correction_method} (α = {analysis.alpha})
          </p>

          <div className="panel-body">
            <div className="chart-wrap">
              <Boxplot row={row} test={test} showPoints={showPoints} />
            </div>

            <div className="side">
              <label className="check">
                <input type="checkbox" checked={showPoints} onChange={(e) => setShowPoints(e.target.checked)} />
                Show individual samples
              </label>

              <div className={`test-card ${test === "welch" ? "on" : ""}`}>
                <strong>Welch's t-test</strong>
                <div>t = {fmt(row.welch_t_stat, 2)}, df = {fmt(row.welch_df, 1)}</div>
                <div>p = {fmt(row.welch_p_value, 4)} · adj. p = {fmt(row.welch_p_adjusted, 4)}</div>
                <div>{ciPct}% CI: [{fmt(row.welch_ci_low, 2)}, {fmt(row.welch_ci_high, 2)}]</div>
              </div>
              <div className={`test-card ${test === "mwu" ? "on" : ""}`}>
                <strong>Mann-Whitney U</strong>
                <div>U = {fmt(row.mwu_u_stat, 1)}</div>
                <div>p = {fmt(row.mwu_p_value, 4)} · adj. p = {fmt(row.mwu_p_adjusted, 4)}</div>
                <div>{ciPct}% CI (HL): [{fmt(row.mwu_ci_low, 2)}, {fmt(row.mwu_ci_high, 2)}]</div>
              </div>

              <p className="muted small">
                Hedges' g = {fmt(row.effect_size, 2)} · diff = {fmt(row.mean_diff, 2)} pts (yes − no).
                * adj. p &lt; α, ** &lt; 0.01, *** &lt; 0.001, ns = not significant. Box = IQR, line = median,
                whiskers = 1.5×IQR, hollow dots = outliers.
              </p>
            </div>
          </div>
        </>
      )}
    </section>
  );
}