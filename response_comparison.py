#!/usr/bin/env python3
"""
Compare relative frequencies of cell populations between responders (yes) and
non-responders (no) among patients treated with a given drug (default: miraclib),
restricted to one sample type (default: PBMC).

For each population, runs Welch's t-test and the Mann-Whitney U test side by side,
corrects each family of p-values across populations, and stores everything in
two tables: `analyses` (one row per run) and `population_results` (one row per
population per run, including the summary statistics needed for boxplots).

Requires: numpy, scipy   (pip install numpy scipy)

Usage:
    python response_comparison.py
"""
import sqlite3
import sys
import json
from datetime import datetime, timezone

import numpy as np

from utils.stats_helper import box_stats, hedges_g, welch_test, mann_whitney, adjust_pvalues, _f

POPULATIONS = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]
GROUP_A, GROUP_B = "yes", "no"  # response values compared (mean_diff = yes - no)
GROUPS = (GROUP_A, GROUP_B)
BOX_FIELDS = ["min", "q1", "median", "q3", "max", "whisker_low", "whisker_high"]
CORRECTION_NAMES = {"bh": "benjamini-hochberg", "bonferroni": "bonferroni"}

db_path = "cell-count.db"


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def _box_columns_sql():
    cols = []
    for g in GROUPS:
        cols += [f"{f}_{g} REAL" for f in BOX_FIELDS]
        cols.append(f"outliers_{g} TEXT")  # JSON array of values outside the whiskers
        cols.append(f"values_{g} TEXT")    # JSON array of all raw percentages
    return ",\n    ".join(cols)

CREATE_COMPARISON_TABLES = f"""
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at             TEXT    NOT NULL,
    treatment          TEXT    NOT NULL,
    sample_type        TEXT    NOT NULL,
    condition          TEXT    NOT NULL,
    group_column       TEXT    NOT NULL,
    group_a            TEXT    NOT NULL,
    group_b            TEXT    NOT NULL,
    alpha              REAL    NOT NULL,
    correction_method  TEXT    NOT NULL,
    n_samples_used     INTEGER,
    n_excluded         INTEGER,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS population_results (
    analysis_id  INTEGER NOT NULL REFERENCES analyses(analysis_id) ON DELETE CASCADE,
    population   TEXT    NOT NULL,

    -- descriptive statistics (percentage scale)
    n_yes INTEGER, n_no INTEGER,
    mean_yes REAL, mean_no REAL,
    sd_yes REAL,   sd_no REAL,
    mean_diff REAL,            -- yes minus no
    effect_size REAL,          -- Hedges' g (yes vs no)

    -- Welch's t-test
    welch_t_stat      REAL,
    welch_df          REAL,
    welch_p_value     REAL,
    welch_p_adjusted  REAL,
    welch_ci_low      REAL,    -- CI for mean difference (yes - no), level 1 - alpha
    welch_ci_high     REAL,
    welch_significant INTEGER CHECK (welch_significant IN (0, 1)),

    -- Mann-Whitney U test
    mwu_u_stat        REAL,    -- U statistic for the "yes" group
    mwu_p_value       REAL,
    mwu_p_adjusted    REAL,
    mwu_hl_estimate   REAL,    -- Hodges-Lehmann location shift (yes - no)
    mwu_ci_low        REAL,    -- Hodges-Lehmann CI, level 1 - alpha
    mwu_ci_high       REAL,
    mwu_significant   INTEGER CHECK (mwu_significant IN (0, 1)),

    -- boxplot data, per group
    {_box_columns_sql()},

    PRIMARY KEY (analysis_id, population)
);

CREATE VIEW IF NOT EXISTS significant_results AS
SELECT a.analysis_id, a.run_at, a.treatment, a.sample_type, a.condition, r.*
FROM population_results r JOIN analyses a USING (analysis_id)
WHERE r.welch_significant = 1 OR r.mwu_significant = 1;
"""

def create_comparison_tables(conn):
    conn.executescript(CREATE_COMPARISON_TABLES)

# --------------------------------------------------------------------------- #
# Pull comparisons data
# --------------------------------------------------------------------------- #
def fetch_comparison_data(conn, condition, treatment, sample_type, timepoint):
    """
    Returns (data, n_used, n_excluded), where
      data[population][group] = list of percentages
    Only samples matching treatment + sample_type with a yes/no response and
    non-null percentages are used. n_excluded counts matching samples that were
    dropped (e.g. missing/other response).
    """
    where = "LOWER(TRIM(s.treatment)) = LOWER(?) AND LOWER(TRIM(s.condition)) = LOWER(?) AND LOWER(TRIM(p.sample_type)) = LOWER(?)"
    params = [treatment, condition, sample_type]
    if timepoint is not None:
        where += " AND p.time_from_treatment_start = ?"
        params.append(timepoint)

    try:
        rows = conn.execute(
            f"""
            SELECT r.sample, r.population, r.percentage, LOWER(TRIM(s.response)) AS response
            FROM relative_frequencies r
            JOIN samples  p ON r.sample  = p.sample
            JOIN subjects s ON p.subject = s.subject
            WHERE {where}
              AND LOWER(TRIM(s.response)) IN ('{GROUP_A}', '{GROUP_B}')
              AND r.percentage IS NOT NULL
            """,
            params,
        ).fetchall()
    except sqlite3.OperationalError as e:
        sys.exit(f"Database error: {e}\n(Did you run relative_frequencies.py on this database?)")

    n_matching = conn.execute(
        f"SELECT COUNT(*) FROM samples p JOIN subjects s ON p.subject = s.subject WHERE {where}",
        params,
    ).fetchone()[0]

    data = {pop: {g: [] for g in GROUPS} for pop in POPULATIONS}
    used_samples = set()
    for sample, population, pct, response in rows:
        if population in data:
            data[population][response].append(pct)
            used_samples.add(sample)

    return data, len(used_samples), n_matching - len(used_samples)


# --------------------------------------------------------------------------- #
# Stats helper
# --------------------------------------------------------------------------- #
def analyze_population(population, yes, no, alpha):
    """Compute all columns for one population (except adjusted p-values/significance)."""
    groups = {GROUP_A: np.asarray(yes, float), GROUP_B: np.asarray(no, float)}
    row = {"population": population}

    for g, a in groups.items():
        row[f"n_{g}"] = len(a)
        row[f"mean_{g}"] = _f(a.mean()) if len(a) else None
        row[f"sd_{g}"] = _f(a.std(ddof=1)) if len(a) > 1 else None
        if len(a):
            b = box_stats(a)
            for f in BOX_FIELDS:
                row[f"{f}_{g}"] = b[f]
            row[f"outliers_{g}"] = b["outliers"]
            row[f"values_{g}"] = json.dumps([float(v) for v in a])
        else:
            for f in BOX_FIELDS:
                row[f"{f}_{g}"] = None
            row[f"outliers_{g}"] = row[f"values_{g}"] = None

    x, y = groups[GROUP_A], groups[GROUP_B]
    row["mean_diff"] = _f(x.mean() - y.mean()) if len(x) and len(y) else None

    tests_ok = len(x) >= 2 and len(y) >= 2
    if tests_ok:
        row["effect_size"] = hedges_g(x, y)
        (row["welch_t_stat"], row["welch_df"], row["welch_p_value"],
         row["welch_ci_low"], row["welch_ci_high"]) = welch_test(x, y, alpha)
        (row["mwu_u_stat"], row["mwu_p_value"], row["mwu_hl_estimate"],
         row["mwu_ci_low"], row["mwu_ci_high"]) = mann_whitney(x, y, alpha)
    else:
        for k in ["effect_size", "welch_t_stat", "welch_df", "welch_p_value", "welch_ci_low",
                  "welch_ci_high", "mwu_u_stat", "mwu_p_value", "mwu_hl_estimate",
                  "mwu_ci_low", "mwu_ci_high"]:
            row[k] = None
    return row

def run_comparison_tests(data, alpha, correction):
    results = [analyze_population(p, data[p][GROUP_A], data[p][GROUP_B], alpha)
               for p in POPULATIONS]
    for prefix in ("welch", "mwu"):
        adj = adjust_pvalues([r[f"{prefix}_p_value"] for r in results], correction)
        for r, a in zip(results, adj):
            r[f"{prefix}_p_adjusted"] = a
            r[f"{prefix}_significant"] = None if a is None else int(a < alpha)
    return results


# --------------------------------------------------------------------------- #
# Print
# --------------------------------------------------------------------------- #
def _fmt(x, spec=".4f"):
    return "NA" if x is None else format(x, spec)


def print_comparisons(results, header_lines):
    print("\n".join(header_lines))
    print()
    print(f"{'population':<11}{'n(y/n)':>9}{'mean yes':>10}{'mean no':>10}{'diff':>9}{'g':>8}")
    for r in results:
        print(f"{r['population']:<11}{str(r['n_yes']) + '/' + str(r['n_no']):>9}"
              f"{_fmt(r['mean_yes'], '.2f'):>10}{_fmt(r['mean_no'], '.2f'):>10}"
              f"{_fmt(r['mean_diff'], '.2f'):>9}{_fmt(r['effect_size'], '.2f'):>8}")

    print("\nWelch's t-test")
    print(f"{'population':<11}{'t':>9}{'df':>8}{'p':>11}{'p_adj':>11}  {'CI (yes - no)':<22}sig")
    for r in results:
        ci = f"[{_fmt(r['welch_ci_low'], '.2f')}, {_fmt(r['welch_ci_high'], '.2f')}]"
        print(f"{r['population']:<11}{_fmt(r['welch_t_stat'], '.3f'):>9}{_fmt(r['welch_df'], '.1f'):>8}"
              f"{_fmt(r['welch_p_value']):>11}{_fmt(r['welch_p_adjusted']):>11}  {ci:<22}"
              f"{'*' if r['welch_significant'] else ''}")

    print("\nMann-Whitney U test")
    print(f"{'population':<11}{'U':>9}{'p':>11}{'p_adj':>11}  {'HL shift [CI]':<30}sig")
    for r in results:
        hl = (f"{_fmt(r['mwu_hl_estimate'], '.2f')} "
              f"[{_fmt(r['mwu_ci_low'], '.2f')}, {_fmt(r['mwu_ci_high'], '.2f')}]")
        print(f"{r['population']:<11}{_fmt(r['mwu_u_stat'], '.1f'):>9}{_fmt(r['mwu_p_value']):>11}"
              f"{_fmt(r['mwu_p_adjusted']):>11}  {hl:<30}{'*' if r['mwu_significant'] else ''}")
    print("\n* = adjusted p-value below alpha")


# --------------------------------------------------------------------------- #
# Write the comparison results (one function per table)
# --------------------------------------------------------------------------- #
def write_comparison_analysis(conn, *, treatment, sample_type, condition, alpha, correction, n_used, n_excluded, notes):
    """Insert one row into `analyses`; returns the new analysis_id."""
    cur = conn.execute(
        """INSERT INTO analyses
           (run_at, treatment, sample_type, condition, group_column, group_a, group_b,
            alpha, correction_method, n_samples_used, n_excluded, notes)
           VALUES (?, ?, ?, ?, 'response', ?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), treatment, sample_type,
         condition, GROUP_A, GROUP_B, alpha, CORRECTION_NAMES[correction], n_used, n_excluded, notes),
    )
    return cur.lastrowid


def write_population_results(conn, analysis_id, results):
    """Insert one row per population into `population_results`."""
    for r in results:
        row = {"analysis_id": analysis_id, **r}
        cols = list(row)
        conn.execute(
            f"INSERT INTO population_results ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            [row[c] for c in cols],
        )


# --------------------------------------------------------------------------- #
# Application Entry point
# --------------------------------------------------------------------------- #
def main():
    args = {
        "db": db_path,
        "condition": "melanoma",
        "treatment": "miraclib",
        "sample_type": "PBMC",
        "alpha": 0.05,
        "correction": "bh",
        "timepoint": None,
    }

    conn = sqlite3.connect(db_path)

    data, n_used, n_excluded = fetch_comparison_data(conn, args["condition"], args['treatment'], args["sample_type"],
                                                     args["timepoint"])
    if n_used == 0:
        sys.exit("No samples matched the filters.")

    results = run_comparison_tests(data, args["alpha"], args["correction"])

    if args["timepoint"] is None:
        tp_note = ("All timepoints pooled: multiple samples per subject are treated as "
                   "independent (pseudoreplication).")
    else:
        tp_note = f"Only samples with time_from_treatment_start = {args["timepoint"]:g}."
    notes = (f"{tp_note} CIs at level {1 - args["alpha"]:g}; MWU CI is Hodges-Lehmann (normal "
             f"approximation). Quartiles use linear interpolation; whiskers are Tukey 1.5xIQR.")

    print_comparisons(results, [
        f"Treatment: {args["treatment"]} | sample_type: {args["sample_type"]} | condition: {args["condition"]} | "
        f"{GROUP_A} vs {GROUP_B} ({CORRECTION_NAMES[args["correction"]]} correction, alpha={args["alpha"]})",
        f"Samples used: {n_used} | matching samples excluded (no yes/no response): {n_excluded}",
        tp_note,
    ])

    create_comparison_tables(conn)
    with conn:  # one transaction for both tables
        analysis_id = write_comparison_analysis(
            conn, treatment=args["treatment"], sample_type=args["sample_type"], condition=args["condition"],
            alpha=args["alpha"], correction=args["correction"], n_used=n_used, n_excluded=n_excluded,
            notes=notes)
        write_population_results(conn, analysis_id, results)
    print(f"\nSaved as analysis_id={analysis_id} in {args["db"]} "
          f"(tables: analyses, population_results; view: significant_results)")

    conn.close()

if __name__ == "__main__":
    main()