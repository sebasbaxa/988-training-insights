"""Analysis functions on the cleaned survey frame produced by `cleaning.clean_survey`.

Conventions
- Likert items are scored 1 (Strongly disagree) .. 5 (Strongly agree).
- "Confident" / "agree" = a rating of 4 or 5.
- Pre-training ratings are *retrospective* (asked after the training), so gains
  are self-reported change, not a true pre/post test.
- Groups smaller than `min_n` are suppressed (privacy + unstable estimates);
  groups under 30 are labelled low-confidence.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from .cleaning import KNOWLEDGE_ITEMS, TRAINING_ITEMS

LOW_CONFIDENCE_N = 30
DEFAULT_MIN_N = 10

GROUP_DIMENSIONS = {
    "county": "County",
    "role": "Role",
    "role_group": "Student vs adult",
    "language": "Survey language",
}


def _f(s: pd.Series) -> np.ndarray:
    return pd.to_numeric(s, errors="coerce").astype(float).dropna().to_numpy()


def mean_ci(values, conf: float = 0.95):
    """Mean with a t-based confidence interval. Returns (mean, low, high, n)."""
    x = _f(pd.Series(values))
    n = len(x)
    if n == 0:
        return (np.nan, np.nan, np.nan, 0)
    m = x.mean()
    if n < 2:
        return (m, np.nan, np.nan, n)
    h = stats.sem(x) * stats.t.ppf((1 + conf) / 2, n - 1)
    return (m, m - h, m + h, n)


def pct_ci(successes: int, n: int, conf: float = 0.95):
    """Wilson score interval for a proportion, returned as percentages."""
    if n == 0:
        return (np.nan, np.nan, np.nan)
    z = stats.norm.ppf((1 + conf) / 2)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (100 * p, 100 * (centre - half), 100 * (centre + half))


def reliability(n: int, min_n: int = DEFAULT_MIN_N) -> str:
    if n < min_n:
        return "Suppressed"
    if n < LOW_CONFIDENCE_N:
        return "Low confidence"
    return "OK"


def apply_filters(df: pd.DataFrame, exclude_flagged: bool = True, counties=None, roles=None,
                  languages=None, date_range=None) -> pd.DataFrame:
    out = df
    if exclude_flagged:
        out = out[~out["flag_any"]]
    if counties:
        out = out[out["county"].isin(counties)]
    if roles:
        out = out[out["role"].isin(roles)]
    if languages:
        out = out[out["language"].isin(languages)]
    if date_range:
        lo, hi = (pd.Timestamp(d) for d in date_range)
        out = out[(out["training_date"] >= lo) & (out["training_date"] <= hi)]
    return out


# ---------------------------------------------------------------------------
# Headline metrics
# ---------------------------------------------------------------------------
def nps(scores) -> Dict[str, float]:
    """Net Promoter Score: % 9-10 minus % 0-6."""
    x = _f(pd.Series(scores))
    n = len(x)
    if n == 0:
        return {"nps": np.nan, "promoters": np.nan, "passives": np.nan, "detractors": np.nan, "n": 0}
    pro, det = (x >= 9).mean() * 100, (x <= 6).mean() * 100
    return {"nps": pro - det, "promoters": pro, "passives": 100 - pro - det, "detractors": det, "n": n}


def knowledge_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per knowledge item: retrospective pre vs post, with a paired significance test."""
    rows = []
    for key, label in KNOWLEDGE_ITEMS.items():
        pair = df[[f"pre_{key}", f"post_{key}"]].astype(float).dropna()
        pre, post = pair.iloc[:, 0].to_numpy(), pair.iloc[:, 1].to_numpy()
        diff = post - pre
        n = len(pair)
        nz = diff[diff != 0]
        if len(nz) > 0:
            w = stats.wilcoxon(post, pre, zero_method="wilcox")
            p = w.pvalue
            # matched-pairs rank-biserial correlation
            ranks = stats.rankdata(np.abs(nz))
            r_rb = (ranks[nz > 0].sum() - ranks[nz < 0].sum()) / ranks.sum()
        else:
            p, r_rb = np.nan, 0.0
        m, lo, hi, _ = mean_ci(diff)
        rows.append({
            "Item": label,
            "key": key,
            "n": n,
            "Pre mean": pre.mean(),
            "Post mean": post.mean(),
            "Mean gain": m,
            "Gain CI low": lo,
            "Gain CI high": hi,
            "% agree before": (pre >= 4).mean() * 100,
            "% agree after": (post >= 4).mean() * 100,
            "% improved": (diff > 0).mean() * 100,
            "% no change": (diff == 0).mean() * 100,
            "% declined": (diff < 0).mean() * 100,
            "% at ceiling before": (pre == 5).mean() * 100,
            "% still not confident": (post <= 3).mean() * 100,
            "Wilcoxon p": p,
            "Effect size (rank-biserial)": r_rb,
        })
    return pd.DataFrame(rows)


def likert_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Long table of % per rating, for each knowledge item, before and after."""
    rows = []
    for key, label in KNOWLEDGE_ITEMS.items():
        for when in ("pre", "post"):
            s = df[f"{when}_{key}"].astype(float).dropna()
            counts = s.value_counts(normalize=True) * 100
            for score in range(1, 6):
                rows.append({"Item": label, "When": "Before" if when == "pre" else "After",
                             "Rating": score, "Percent": counts.get(float(score), 0.0), "n": len(s)})
    return pd.DataFrame(rows)


def training_quality(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col, label in TRAINING_ITEMS.items():
        s = df[col].astype(float).dropna()
        rows.append({"Item": label, "n": len(s), "Mean": s.mean(),
                     "% agree": (s >= 4).mean() * 100 if len(s) else np.nan,
                     "% disagree": (s <= 2).mean() * 100 if len(s) else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Group comparisons
# ---------------------------------------------------------------------------
def group_summary(df: pd.DataFrame, by: str, min_n: int = DEFAULT_MIN_N) -> pd.DataFrame:
    rows = []
    for g, sub in df.groupby(by, dropna=False):
        n = len(sub)
        rel = reliability(n, min_n)
        row = {"Group": g, "n": n, "Reliability": rel}
        if rel != "Suppressed":
            gm, glo, ghi, _ = mean_ci(sub["gain_mean"])
            conf_when = (sub["post_when"].astype(float) >= 4)
            pw, pwlo, pwhi = pct_ci(int(conf_when.sum()), int(sub["post_when"].notna().sum()))
            rec = nps(sub["recommend"])
            call = _f(sub["call_988"])
            row.update({
                "Pre mean": float(_f(sub["pre_mean"]).mean()),
                "Post mean": float(_f(sub["post_mean"]).mean()),
                "Mean gain": gm, "Gain CI low": glo, "Gain CI high": ghi,
                "% know when to use 988": pw, "CI low %": pwlo, "CI high %": pwhi,
                "NPS": rec["nps"] if rec["n"] >= min_n else np.nan,
                "Recommend n": rec["n"],
                "Likely to call 988 (0-10)": call.mean() if len(call) >= min_n else np.nan,
                "Call-988 n": len(call),
            })
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("n", ascending=False).reset_index(drop=True)


GAP_METRICS = {
    "post_mean": "post-training confidence (avg of 3 items, 1-5)",
    "gain_mean": "self-reported gain (1-5 scale points)",
    "post_when": "'I know when to use 988' rating (1-5)",
    "recommend": "likelihood to recommend (0-10)",
    "call_988": "likelihood to call 988 (0-10)",
}


def _bh(pvals: Iterable[float]) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values."""
    p = np.asarray(list(pvals), dtype=float)
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(adj, 0, 1)
    return out


def gap_finder(df: pd.DataFrame, dims: Optional[List[str]] = None, min_n: int = DEFAULT_MIN_N,
               alpha: float = 0.05) -> pd.DataFrame:
    """Compare every sufficiently large group against everyone else.

    Mann-Whitney U per (group, metric), Benjamini-Hochberg correction across all
    tests, and an explicit strength label so thin findings are not oversold.
    """
    dims = dims or list(GROUP_DIMENSIONS)
    rows = []
    for dim in dims:
        for g, sub in df.groupby(dim):
            rest = df[df[dim] != g]
            for metric, label in GAP_METRICS.items():
                a, b = _f(sub[metric]), _f(rest[metric])
                if len(a) < min_n or len(b) < min_n:
                    continue
                u = stats.mannwhitneyu(a, b, alternative="two-sided")
                rows.append({
                    "Dimension": GROUP_DIMENSIONS.get(dim, dim), "Group": g, "Metric": label,
                    "metric_key": metric, "Group n": len(a), "Rest n": len(b),
                    "Group mean": a.mean(), "Rest mean": b.mean(), "Difference": a.mean() - b.mean(),
                    # rank-biserial effect size from U
                    "Effect size": 2 * u.statistic / (len(a) * len(b)) - 1,
                    "p": u.pvalue,
                })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["p (BH-adjusted)"] = _bh(out["p"])

    def strength(r):
        if r["p (BH-adjusted)"] >= alpha:
            return "Not significant"
        if r["Group n"] < LOW_CONFIDENCE_N:
            return "Significant but thin (n<30)"
        return "Strong" if abs(r["Effect size"]) >= 0.2 else "Significant, small effect"

    out["Evidence"] = out.apply(strength, axis=1)
    out["Direction"] = np.where(out["Difference"] < 0, "Lower", "Higher")
    out["Finding"] = out.apply(
        lambda r: f"{r['Group']} (n={r['Group n']}) score {abs(r['Difference']):.2f} points "
                  f"{r['Direction'].lower()} than everyone else on {r['Metric']}.",
        axis=1)
    return out.sort_values(["p (BH-adjusted)", "Effect size"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Over time / by session
# ---------------------------------------------------------------------------
def monthly_trend(df: pd.DataFrame, min_n: int = DEFAULT_MIN_N) -> pd.DataFrame:
    rows = []
    for month, sub in df.groupby("training_month"):
        n = len(sub)
        rec = nps(sub["recommend"])
        rows.append({"Month": month, "n": n, "Reliability": reliability(n, min_n),
                     "Pre mean": _f(sub["pre_mean"]).mean(), "Post mean": _f(sub["post_mean"]).mean(),
                     "Mean gain": _f(sub["gain_mean"]).mean(), "NPS": rec["nps"]})
    out = pd.DataFrame(rows)
    if not out.empty:
        mask = out["Reliability"] == "Suppressed"
        out.loc[mask, ["Pre mean", "Post mean", "Mean gain", "NPS"]] = np.nan
    return out


def session_review(df: pd.DataFrame, min_n: int = DEFAULT_MIN_N) -> pd.DataFrame:
    """Sessions (county + training date) with at least min_n responses, flagging
    ones whose post-training confidence or presenter rating sits well below the
    overall level (more than 1 SD of session means below the session average)."""
    g = df.groupby("session_id")
    tbl = pd.DataFrame({
        "County": g["county"].first(),
        "Training date": g["training_date"].first(),
        "n": g.size(),
        "Post mean": g["post_mean"].apply(lambda s: _f(s).mean()),
        "Mean gain": g["gain_mean"].apply(lambda s: _f(s).mean()),
        "Presenter engaged": g["presenter_engaged"].apply(lambda s: _f(s).mean()),
        "NPS": g["recommend"].apply(lambda s: nps(s)["nps"]),
    }).reset_index()
    tbl = tbl[tbl["n"] >= min_n].copy()
    if tbl.empty:
        tbl["Review"] = []
        return tbl
    flags = []
    for col in ["Post mean", "Presenter engaged", "NPS"]:
        thr = tbl[col].mean() - tbl[col].std()
        flags.append(np.where(tbl[col] < thr, f"low {col.lower()}", ""))
    tbl["Review"] = ["; ".join(x for x in parts if x) for parts in zip(*flags)]
    return tbl.sort_values("Training date").reset_index(drop=True)
