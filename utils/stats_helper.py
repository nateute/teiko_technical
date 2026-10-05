import json
import math

import numpy as np
from scipy import stats

# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def _f(x):
    """numpy/NaN-safe float for SQLite (NaN/inf -> None)."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None

def box_stats(values):
    """Five-number summary with Tukey (1.5 x IQR) whiskers and outliers."""
    v = np.asarray(values, dtype=float)
    q1, med, q3 = np.percentile(v, [25, 50, 75])  # linear interpolation
    iqr = q3 - q1
    lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    inside = v[(v >= lo_fence) & (v <= hi_fence)]
    outliers = np.sort(v[(v < lo_fence) | (v > hi_fence)])
    return {
        "min": _f(v.min()), "q1": _f(q1), "median": _f(med), "q3": _f(q3), "max": _f(v.max()),
        "whisker_low": _f(inside.min()), "whisker_high": _f(inside.max()),
        "outliers": json.dumps([float(o) for o in outliers]),
    }


def welch_test(x, y, alpha):
    """Welch's t-test. Returns t, df, p, and CI for mean(x) - mean(y)."""
    n1, n2 = len(x), len(y)
    v1, v2 = x.var(ddof=1) / n1, y.var(ddof=1) / n2
    se = math.sqrt(v1 + v2)
    if se == 0:  # both groups constant
        return None, None, None, None, None
    df = (v1 + v2) ** 2 / (v1 ** 2 / (n1 - 1) + v2 ** 2 / (n2 - 1))
    res = stats.ttest_ind(x, y, equal_var=False)
    diff = x.mean() - y.mean()
    margin = stats.t.ppf(1 - alpha / 2, df) * se
    return _f(res.statistic), _f(df), _f(res.pvalue), _f(diff - margin), _f(diff + margin)


def mann_whitney(x, y, alpha):
    """
    Mann-Whitney U (two-sided). Also returns the Hodges-Lehmann shift estimate and
    its CI, computed from sorted pairwise differences with a normal approximation
    (no tie correction), so the CI is a close approximation rather than exact.
    """
    res = stats.mannwhitneyu(x, y, alternative="two-sided")
    n1, n2 = len(x), len(y)
    diffs = np.sort((x[:, None] - y[None, :]).ravel())
    N = n1 * n2
    z = stats.norm.ppf(1 - alpha / 2)
    c = z * math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    k = max(int(math.floor(N / 2 - c)), 0)
    return (_f(res.statistic), _f(res.pvalue), _f(np.median(diffs)),
            _f(diffs[k]), _f(diffs[N - 1 - k]))


def hedges_g(x, y):
    n1, n2 = len(x), len(y)
    sp = math.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / (n1 + n2 - 2))
    if sp == 0:
        return None
    return _f((x.mean() - y.mean()) / sp * (1 - 3 / (4 * (n1 + n2) - 9)))


def adjust_pvalues(pvals, method):
    """Adjust a list of p-values (None entries are ignored). method: 'bh' or 'bonferroni'."""
    out = [None] * len(pvals)
    idx = [i for i, p in enumerate(pvals) if p is not None]
    if not idx:
        return out
    p = np.array([pvals[i] for i in idx])
    m = len(p)
    if method == "bonferroni":
        adj = np.minimum(p * m, 1.0)
    else:  # Benjamini-Hochberg
        order = np.argsort(p)
        ranked = p[order] * m / np.arange(1, m + 1)
        adj_sorted = np.minimum(np.minimum.accumulate(ranked[::-1])[::-1], 1.0)
        adj = np.empty(m)
        adj[order] = adj_sorted
    for i, a in zip(idx, adj):
        out[i] = float(a)
    return out
