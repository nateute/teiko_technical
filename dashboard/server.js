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

app.listen(PORT, () => console.log(`API on :${PORT}, reading ${DB_PATH}`));
