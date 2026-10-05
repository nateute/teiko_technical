// Tiny read-only API that serves the relative_frequencies table from cell-count.db.
import express from "express";
import Database from "better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Default: cell-count.db in the repo root (one level above /dashboard).
// Override with:  DB_PATH=/path/to/cell-count.db npm run dev
const DB_PATH = process.env.DB_PATH || path.resolve(__dirname, "..", "cell-count.db");
const PORT = process.env.PORT || 3001;

if (!fs.existsSync(DB_PATH)) {
  console.error(`Database not found at ${DB_PATH}. Set DB_PATH or move cell-count.db.`);
  process.exit(1);
}

const db = new Database(DB_PATH, { readonly: true, fileMustExist: true });
const app = express();

app.get("/api/relative-frequencies", (_req, res) => {
  try {
    const rows = db
      .prepare(
        `SELECT sample, total_count, population, count, percentage
         FROM relative_frequencies
         ORDER BY sample, population`
      )
      .all();
    res.json(rows);
  } catch (err) {
    // Most likely cause: relative_frequencies.py hasn't been run yet.
    res.status(500).json({ error: err.message });
  }
});

const POP_ORDER = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"];
const JSON_COLS = ["values_yes", "values_no", "outliers_yes", "outliers_no"];
const tableExists = (name) =>
  !!db.prepare("SELECT 1 FROM sqlite_master WHERE name = ? AND type IN ('table','view')").get(name);

// All saved runs of response_analysis.py, newest first.
app.get("/api/analyses", (_req, res) => {
  try {
    if (!tableExists("analyses")) return res.json([]);
    res.json(db.prepare("SELECT * FROM analyses ORDER BY analysis_id DESC").all());
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Per-population test results + boxplot data for one run.
app.get("/api/analyses/:id/results", (req, res) => {
  try {
    const id = Number(req.params.id);
    if (!Number.isInteger(id)) return res.status(400).json({ error: "Invalid analysis id" });
    if (!tableExists("population_results")) return res.json([]);
    const rows = db.prepare("SELECT * FROM population_results WHERE analysis_id = ?").all(id);
    for (const r of rows) {
      for (const c of JSON_COLS) r[c] = r[c] ? JSON.parse(r[c]) : [];
    }
    rows.sort((a, b) => POP_ORDER.indexOf(a.population) - POP_ORDER.indexOf(b.population));
    res.json(rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// Baseline cohort counts saved by subset_analysis.py (latest run, or ?run_id=N).
app.get("/api/subset-analysis", (req, res) => {
  try {
    if (!tableExists("subset_analysis")) return res.json(null);
    const runId = req.query.run_id !== undefined
      ? Number(req.query.run_id)
      : db.prepare("SELECT MAX(run_id) AS id FROM subset_analysis").get().id;
    if (runId == null || !Number.isInteger(runId)) return res.json(null);

    const rows = db
      .prepare(
        `SELECT * FROM subset_analysis WHERE run_id = ?
         ORDER BY category, n_subjects DESC, level`
      )
      .all(runId);
    if (rows.length === 0) return res.json(null);

    const { run_at, treatment, sample_type, condition, time_from_treatment_start } = rows[0];
    const out = {
      run_id: runId, run_at, treatment, sample_type, condition,
      time_from_treatment_start, total: 0, counts: { project: [], response: [], sex: [] },
    };
    for (const r of rows) {
      if (r.category === "total") out.total = r.n_subjects;
      else out.counts[r.category].push({ level: r.level, n_subjects: r.n_subjects, percent: r.percent });
    }
    res.json(out);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(PORT, () => console.log(`API on :${PORT}, reading ${DB_PATH}`));