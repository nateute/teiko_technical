#!/usr/bin/env python3
"""
Part 2: Compute relative frequencies of each cell population per sample, write them to
a `relative_frequencies` table, and print a summary.

Part 3:

Part 4:

Usage:
    python analyze_data.py
"""

import sqlite3
import sys

POPULATIONS = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]

db_path = "cell-count.db"

# Step 1: pull sample + counts and compute total_count per sample.
# NULL counts are treated as 0 for the total.
# Step 2: unpivot (wide -> long) with one SELECT per population, then compute
# percentage = 100 * count / total_count. Rows with a NULL count are skipped,
# and percentage is NULL if the total is 0 (avoids division by zero).
totals_cte = f"""
WITH totals AS (
    SELECT sample,
           {', '.join(POPULATIONS)},
           {' + '.join(f'COALESCE({p}, 0)' for p in POPULATIONS)} AS total_count
    FROM samples
)
"""

long_selects = "\nUNION ALL\n".join(
    f"""SELECT sample, total_count, '{p}' AS population, {p} AS count,
       CASE WHEN total_count > 0 THEN 100.0 * {p} / total_count END AS percentage
FROM totals WHERE {p} IS NOT NULL"""
    for p in POPULATIONS
)

FREQ_QUERY = totals_cte + long_selects + "\nORDER BY sample, population;"

CREATE_RELFREQ_TABLE = """
DROP TABLE IF EXISTS relative_frequencies;
CREATE TABLE relative_frequencies (
    sample       TEXT    NOT NULL REFERENCES samples(sample),
    total_count  INTEGER NOT NULL CHECK (total_count >= 0),
    population   TEXT    NOT NULL
                 CHECK (population IN ('b_cell','cd8_t_cell','cd4_t_cell','nk_cell','monocyte')),
    count        INTEGER NOT NULL CHECK (count >= 0),
    percentage   REAL    CHECK (percentage IS NULL OR percentage BETWEEN 0 AND 100),
    PRIMARY KEY (sample, population)
);
CREATE INDEX idx_relfreq_population ON relative_frequencies(population);
"""



def main():
    # Part 2: determine the relative frequency of each cell type in each sample.
    # This results in a summary table with n_samples*n_cell_populations rows and columns:
    #   sample, total_count, population, count, percentage
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    rows = conn.execute(FREQ_QUERY).fetchall()

    with conn:  # single transaction
        conn.executescript(CREATE_RELFREQ_TABLE)
        conn.executemany(
            "INSERT INTO relative_frequencies "
            "(sample, total_count, population, count, percentage) VALUES (?,?,?,?,?)",
            rows,
        )

    # ---- Summary ----
    n_rows, n_samples = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT sample) FROM relative_frequencies"
    ).fetchone()
    print(f"Wrote {n_rows} rows ({n_samples} samples x populations) "
          f"to table 'relative_frequencies' in {db_path}\n")

    #print("Percentage by population (across samples):")
    #print(f"{'population':<12}{'n':>5}{'mean %':>10}{'min %':>10}{'max %':>10}")
    #for pop, n, mean, lo, hi in conn.execute("""
    #        SELECT population, COUNT(*), AVG(percentage), MIN(percentage), MAX(percentage)
    #        FROM relative_frequencies GROUP BY population ORDER BY population
    #    """):
    #    print(f"{pop:<12}{n:>5}{mean:>10.2f}{lo:>10.2f}{hi:>10.2f}")

    #print("\nFirst 10 rows:")
    #print(f"{'sample':<10}{'total_count':>8}  {'population':<12}{'count':>8}{'pct':>9}")
    #for s, tot, pop, cnt, pct in conn.execute(
    #        "SELECT sample, total_count, population, count, percentage "
    #        "FROM relative_frequencies ORDER BY sample, population LIMIT 10"
    #):
    #    pct_txt = f"{pct:.2f}" if pct is not None else "NA"
    #    print(f"{s:<10}{tot:>8}  {pop:<12}{cnt:>8}{pct_txt:>9}")

    # ---- Sanity check: percentages per sample should sum to ~100 ----
    percentage_error = conn.execute("""
            SELECT sample, SUM(percentage) FROM relative_frequencies
            WHERE percentage IS NOT NULL
            GROUP BY sample HAVING ABS(SUM(percentage) - 100) > 1e-6
        """).fetchall()
    if percentage_error:
        print(f"\nWARNING: {len(bad)} sample(s) whose percentages do not sum to 100 "
              f"(likely samples with NULL counts): {bad[:5]}")
    else:
        print("\nCheck passed: percentages sum to 100 for every sample.")


    # Part 3: report significant differences in cell relfreq for miraclib responders v. non-responders
    

    # Part 4: stats on melanoma PBMC samples at baseline

    conn.close()

if __name__ == "__main__":
    main()



