#!/usr/bin/env python3
"""
Baseline cohort description: select melanoma / PBMC / miraclib samples at
time_from_treatment_start = 0, count subjects by project, response and sex,
and save the counts to the `subset_analysis` table.

Counting unit is the subject (COUNT(DISTINCT subject)). Missing values are
reported as an explicit 'Unknown' level so every breakdown adds up to the
cohort total.

Usage:
    python analyze_data.py
"""
import sqlite3
import sys

from datetime import datetime, timezone

CATEGORIES = ("project", "response", "sex")  # fixed whitelist (used to build SQL)
EXPECTED_LEVELS = {"response": ["yes", "no"], "sex": ["M", "F"]}  # always reported, even if 0

db_path = "cell-count.db"

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
CREATE_SUBSET_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS subset_analysis (
    run_id                     INTEGER NOT NULL,
    run_at                     TEXT    NOT NULL,
    treatment                  TEXT    NOT NULL,
    sample_type                TEXT    NOT NULL,
    condition                  TEXT    NOT NULL,
    time_from_treatment_start  REAL    NOT NULL,
    category                   TEXT    NOT NULL
                               CHECK (category IN ('total', 'project', 'response', 'sex')),
    level                      TEXT    NOT NULL,   -- e.g. 'prj1', 'yes', 'F', 'Unknown', 'all'
    n_subjects                 INTEGER NOT NULL CHECK (n_subjects >= 0),
    percent                    REAL,               -- share of the cohort total (NULL if total is 0)
    PRIMARY KEY (run_id, category, level)
);
CREATE INDEX IF NOT EXISTS idx_subset_run ON subset_analysis(run_id);
"""

def create_subset_analysis_table(conn):
    conn.executescript(CREATE_SUBSET_ANALYSIS_TABLE)

# --------------------------------------------------------------------------- #
# Query the database for subset analysis
# --------------------------------------------------------------------------- #
# Cohort: melanoma + PBMC + miraclib at the chosen timepoint. Blank/NULL values
# become 'Unknown'; response is lower-cased and sex upper-cased so spelling
# variants collapse into one level.
COHORT_CTE = """
WITH cohort AS (
    SELECT s.subject,
           p.sample,
           COALESCE(NULLIF(TRIM(s.project), ''), 'Unknown')          AS project,
           COALESCE(NULLIF(LOWER(TRIM(s.response)), ''), 'Unknown')  AS response,
           COALESCE(NULLIF(UPPER(TRIM(s.sex)), ''), 'Unknown')       AS sex
    FROM samples p
    JOIN subjects s ON p.subject = s.subject
    WHERE LOWER(TRIM(s.condition))   = LOWER(:condition)
      AND LOWER(TRIM(p.sample_type)) = LOWER(:sample_type)
      AND LOWER(TRIM(s.treatment))   = LOWER(:treatment)
      AND p.time_from_treatment_start = :timepoint
)
"""

def fetch_subset_counts(conn, params):
    """
    Returns a dict:
      {"n_subjects": int, "n_samples": int,
       "project": [(level, n), ...], "response": [...], "sex": [...]}
    """
    n_subjects, n_samples = conn.execute(
        COHORT_CTE + "SELECT COUNT(DISTINCT subject), COUNT(*) FROM cohort", params
    ).fetchone()

    counts = {"n_subjects": n_subjects, "n_samples": n_samples}
    for col in CATEGORIES:
        rows = conn.execute(
            COHORT_CTE
            + f"SELECT {col}, COUNT(DISTINCT subject) AS n FROM cohort "
              f"GROUP BY {col} ORDER BY n DESC, {col}",
            params,
        ).fetchall()
        found = dict(rows)
        for level in EXPECTED_LEVELS.get(col, []):  # make sure yes/no and M/F always appear
            found.setdefault(level, 0)
        counts[col] = sorted(found.items(), key=lambda kv: (-kv[1], kv[0]))
    return counts


# --------------------------------------------------------------------------- #
# Write the subset counts results table
# --------------------------------------------------------------------------- #
def write_subset_analysis(conn, params, counts):
    """Insert one run (a 'total' row plus one row per category level); returns run_id."""
    run_id = conn.execute("SELECT COALESCE(MAX(run_id), 0) + 1 FROM subset_analysis").fetchone()[0]
    run_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = counts["n_subjects"]

    def pct(n):
        return 100.0 * n / total if total else None

    rows = [("total", "all", total)]
    for col in CATEGORIES:
        rows += [(col, level, n) for level, n in counts[col]]

    conn.executemany(
        """INSERT INTO subset_analysis
           (run_id, run_at, treatment, sample_type, condition, time_from_treatment_start,
            category, level, n_subjects, percent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(run_id, run_at, params["treatment"], params["sample_type"], params["condition"],
          params["timepoint"], cat, level, n, pct(n)) for cat, level, n in rows],
    )
    return run_id


# --------------------------------------------------------------------------- #
def print_subset_summary(params, counts):
    total = counts["n_subjects"]
    print(f"Cohort: condition={params['condition']} | sample_type={params['sample_type']} | "
          f"treatment={params['treatment']} | time_from_treatment_start={params['timepoint']:g}")
    print(f"Subjects in cohort: {total}  (matching samples: {counts['n_samples']})")
    if counts["n_samples"] != total:
        print("WARNING: some subjects have more than one matching sample. "
              "Counts below are distinct subjects, not samples.")
    titles = {"project": "By project", "response": "By response", "sex": "By sex"}
    for col in CATEGORIES:
        print(f"\n{titles[col]}")
        for level, n in counts[col]:
            share = f"{100 * n / total:5.1f}%" if total else "   NA"
            print(f"  {level:<12}{n:>5}  {share}")
        check = sum(n for _, n in counts[col])
        assert check == total, f"{col} counts ({check}) do not add up to cohort total ({total})"


# --------------------------------------------------------------------------- #
# One-off question: average B cell count, melanoma males, responders, time 0
# --------------------------------------------------------------------------- #
def average_b_cells(conn, condition="melanoma", sex="M", response="yes", timepoint=0.0):
    """
    Average raw b_cell count over all samples (any sample_type, any treatment)
    from subjects matching condition + sex + response at the given timepoint.
    Samples with a NULL b_cell count are left out. Returns (average, n_samples, n_subjects).
    """
    return conn.execute(
        """
        SELECT AVG(p.b_cell), COUNT(p.b_cell), COUNT(DISTINCT s.subject)
        FROM samples p
                 JOIN subjects s ON p.subject = s.subject
        WHERE LOWER(TRIM(s.condition)) = LOWER(:condition)
          AND UPPER(TRIM(s.sex)) = UPPER(:sex)
          AND LOWER(TRIM(s.response)) = LOWER(:response)
          AND p.time_from_treatment_start = :timepoint
          AND p.b_cell IS NOT NULL
        """,
        {"condition": condition, "sex": sex, "response": response, "timepoint": timepoint},
    ).fetchone()


def print_b_cell_average(conn):
    avg, n_samples, n_subjects = average_b_cells(conn)
    print("\nAverage B cell count: melanoma males, responders, time_from_treatment_start = 0 "
          "(all sample types and treatments)")
    if n_samples == 0:
        print("  No matching samples.")
    else:
        print(f"  Average B cell count: {avg:.2f}  "
              f"(n = {n_samples} samples from {n_subjects} subjects)")


# --------------------------------------------------------------------------- #
# Application Entry point
# --------------------------------------------------------------------------- #
def main():
    params = {
        "condition": "melanoma",
        "sample_type": "PBMC",
        "treatment": "miraclib",
        "timepoint": 0.0,
    }

    conn = sqlite3.connect(db_path)

    try:
        counts = fetch_subset_counts(conn, params)
    except sqlite3.OperationalError as e:
        sys.exit(f"Database error: {e}\n(Did you run load_cell_data.py on this database?)")

    if counts["n_subjects"] == 0:
        sys.exit("No samples matched the cohort filters; nothing written.")

    print_subset_summary(params, counts)

    create_subset_analysis_table(conn)
    with conn:  # one transaction
        run_id = write_subset_analysis(conn, params, counts)
    print(f"\nSaved as run_id={run_id} in table 'subset_analysis' of {db_path}")

    # Bonus question in the Google form:
    print_b_cell_average(conn)
    conn.close()

if __name__ == "__main__":
    main()