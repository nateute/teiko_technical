import { useEffect, useMemo, useState } from "react";
import BoxplotPanel from "./BoxplotPanel.jsx";
import CohortPanel from "./CohortPanel.jsx";

const COLUMNS = [
  { key: "sample", label: "Sample", numeric: false },
  { key: "population", label: "Population", numeric: false },
  { key: "count", label: "Count", numeric: true },
  { key: "total_count", label: "Total count", numeric: true },
  { key: "percentage", label: "Percentage", numeric: true },
];
const PAGE_SIZES = [10, 25, 50, 100];

export default function App() {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("loading"); // loading | ready | error
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [population, setPopulation] = useState("all");
  const [sort, setSort] = useState({ key: "sample", dir: "asc" });
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  useEffect(() => {
    fetch("/api/relative-frequencies")
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.error || r.statusText);
        return body;
      })
      .then((data) => {
        setRows(data);
        setStatus("ready");
      })
      .catch((e) => {
        setError(e.message);
        setStatus("error");
      });
  }, []);

  const populations = useMemo(
    () => [...new Set(rows.map((r) => r.population))].sort(),
    [rows]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const out = rows.filter(
      (r) =>
        (population === "all" || r.population === population) &&
        (!q || r.sample.toLowerCase().includes(q))
    );
    const { key, dir } = sort;
    const sign = dir === "asc" ? 1 : -1;
    // nulls always sort last
    out.sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sign;
    });
    return out;
  }, [rows, search, population, sort]);

  // Mean percentage per population, based on the current filter
  const summary = useMemo(() => {
    const acc = {};
    for (const r of filtered) {
      if (r.percentage == null) continue;
      (acc[r.population] ??= []).push(r.percentage);
    }
    return Object.entries(acc)
      .map(([pop, v]) => ({ pop, mean: v.reduce((a, b) => a + b, 0) / v.length, n: v.length }))
      .sort((a, b) => a.pop.localeCompare(b.pop));
  }, [filtered]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * pageSize, (safePage + 1) * pageSize);

  const toggleSort = (key) => {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
    setPage(0);
  };

  if (status === "loading") return <main className="wrap"><p>Loading…</p></main>;
  if (status === "error")
    return (
      <main className="wrap">
        <h1>Couldn't load data</h1>
        <p className="error">{error}</p>
        <p>Check that the API is running and that <code>relative_frequencies.py</code> has been run on <code>cell-count.db</code>.</p>
      </main>
    );

  return (
    <main className="wrap">
      <h1>Cell population relative frequencies</h1>
      <p className="muted">
        {new Set(rows.map((r) => r.sample)).size} samples · {rows.length} rows
      </p>

      <div className="layout">
      <div className="left">
      <section className="cards">
        {summary.map((s) => (
          <div className="card" key={s.pop}>
            <div className="card-label">{s.pop}</div>
            <div className="card-value">{s.mean.toFixed(1)}%</div>
            <div className="card-sub">mean, n={s.n}</div>
          </div>
        ))}
      </section>

      <section className="controls">
        <input
          type="search"
          placeholder="Search sample ID…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
        />
        <select value={population} onChange={(e) => { setPopulation(e.target.value); setPage(0); }}>
          <option value="all">All populations</option>
          {populations.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}>
          {PAGE_SIZES.map((n) => <option key={n} value={n}>{n} / page</option>)}
        </select>
      </section>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={c.numeric ? "num" : ""}
                  onClick={() => toggleSort(c.key)}
                  aria-sort={sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                >
                  {c.label}
                  <span className="arrow">{sort.key === c.key ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={`${r.sample}-${r.population}`}>
                <td>{r.sample}</td>
                <td>{r.population}</td>
                <td className="num">{r.count.toLocaleString()}</td>
                <td className="num">{r.total_count.toLocaleString()}</td>
                <td className="num pct">
                  {r.percentage == null ? "NA" : (
                    <>
                      <span className="bar" style={{ width: `${r.percentage}%` }} />
                      <span className="pct-text">{r.percentage.toFixed(2)}%</span>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr><td colSpan={COLUMNS.length} className="muted">No matching rows.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <footer className="pager">
        <span className="muted">{filtered.length} rows</span>
        <button disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>‹ Prev</button>
        <span>Page {safePage + 1} / {pageCount}</span>
        <button disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)}>Next ›</button>
      </footer>
      </div>

      <aside className="right">
        <BoxplotPanel />
        <CohortPanel />
      </aside>
      </div>
    </main>
  );
}