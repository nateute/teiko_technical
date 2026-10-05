#!/usr/bin/env python3
"""
Load a flat cell-count CSV into a two-table SQLite database.

    subjects: one row per subject (subject-level attributes)
    samples:  one row per sample  (sample-level attributes + cell counts)

Usage:
    python load_data.py
"""

import csv
import sys
import sqlite3

SUBJECT_COLS = ["project", "condition", "age", "sex", "treatment", "response"]
SAMPLE_COLS = ["sample", "subject", "sample_type", "time_from_treatment_start"]
CELL_COLS = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subjects (
    subject    TEXT PRIMARY KEY,
    project    TEXT,
    condition  TEXT,
    age        INTEGER CHECK (age IS NULL OR age >= 0),
    sex        TEXT,
    treatment  TEXT,
    response   TEXT
);

CREATE TABLE IF NOT EXISTS samples (
    sample                     TEXT PRIMARY KEY,
    subject                    TEXT NOT NULL REFERENCES subjects(subject),
    sample_type                TEXT,
    time_from_treatment_start  INTEGER CHECK (time_from_treatment_start >= 0),
    b_cell      INTEGER CHECK (b_cell      IS NULL OR b_cell      >= 0),
    cd8_t_cell  INTEGER CHECK (cd8_t_cell  IS NULL OR cd8_t_cell  >= 0),
    cd4_t_cell  INTEGER CHECK (cd4_t_cell  IS NULL OR cd4_t_cell  >= 0),
    nk_cell     INTEGER CHECK (nk_cell     IS NULL OR nk_cell     >= 0),
    monocyte    INTEGER CHECK (monocyte    IS NULL OR monocyte    >= 0)
);

CREATE INDEX IF NOT EXISTS idx_samples_subject ON samples(subject);
CREATE INDEX IF NOT EXISTS idx_samples_type    ON samples(sample_type);
CREATE INDEX IF NOT EXISTS idx_subjects_cond   ON subjects(condition);
"""

CSV_PATH = "cell-count.csv"
DB_PATH = "cell-count.db"

def clean(value):
    """Turn empty strings / NA-like values into None (SQL NULL)."""
    if value is None:
        return None
    value = value.strip()
    return None if value == "" or value.upper() in {"NA", "N/A", "NULL"} else value


def main():
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        header = f.readline()
        f.seek(0)
        delimiter = "\t" if header.count("\t") > header.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        required = set(SUBJECT_COLS + SAMPLE_COLS + CELL_COLS)
        missing = required - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"CSV is missing columns: {sorted(missing)}")
        rows = [{k: clean(v) for k, v in r.items()} for r in reader]

    # Check that subject-level attributes are consistent across a subject's rows.
    subjects = {}
    for i, r in enumerate(rows, start=2):  # start=2: header is line 1
        attrs = tuple(r[c] for c in SUBJECT_COLS)
        sid = r["subject"]
        if sid is None:
            sys.exit(f"Line {i}: missing subject ID")
        if sid in subjects and subjects[sid] != attrs:
            sys.exit(
                f"Line {i}: subject {sid!r} has conflicting attributes.\n"
                f"  first seen: {dict(zip(SUBJECT_COLS, subjects[sid]))}\n"
                f"  this row:   {dict(zip(SUBJECT_COLS, attrs))}"
            )
        subjects[sid] = attrs

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    with conn:  # one transaction: all-or-nothing
        conn.executemany(
            f"INSERT OR REPLACE INTO subjects (subject, {', '.join(SUBJECT_COLS)}) "
            f"VALUES (?, {', '.join('?' * len(SUBJECT_COLS))})",
            [(sid, *attrs) for sid, attrs in subjects.items()],
        )

        sample_cols = SAMPLE_COLS + CELL_COLS
        conn.executemany(
            f"INSERT OR REPLACE INTO samples ({', '.join(sample_cols)}) "
            f"VALUES ({', '.join('?' * len(sample_cols))})",
            [tuple(r[c] for c in sample_cols) for r in rows],
        )

    n_sub = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    n_smp = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    print(f"Loaded {n_sub} subjects and {n_smp} samples into {DB_PATH}")

    # Example query: mean cell counts by condition
    #print("\nMean counts by condition:")
    # query = """
    #    SELECT s.condition, COUNT(*) AS n_samples,
    #           ROUND(AVG(p.b_cell), 1), ROUND(AVG(p.cd8_t_cell), 1),
    #           ROUND(AVG(p.cd4_t_cell), 1), ROUND(AVG(p.nk_cell), 1),
    #           ROUND(AVG(p.monocyte), 1)
    #    FROM samples p JOIN subjects s ON p.subject = s.subject
    #    GROUP BY s.condition;
    # """
    #for row in conn.execute(query):
    #    print(row)

    conn.close()


if __name__ == "__main__":
    main()