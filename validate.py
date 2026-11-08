"""Independent check of the dashboard's headline numbers.

Recomputes key statistics straight from the raw Excel file with simple pandas
code (no imports from the `everymind` package's cleaning logic), then compares
them with the pipeline's output. Also builds / scores a hand-coding sample for
the comment themes.

Usage:
    python validate.py                     # numeric checks + create theme sample if missing
    python validate.py --score-themes      # score a filled-in validation/theme_sample.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from everymind import analysis as A
from everymind import themes as T
from everymind.cleaning import load_survey

RAW = Path(__file__).parent / "data" / "survey.xlsx"
SAMPLE = Path(__file__).parent / "validation" / "theme_sample.csv"
SCALE = {"strongly disagree": 1, "disagree": 2, "neither agree nor disagree": 3, "neither agree or disagree": 3,
         "agree": 4, "strongly agree": 5, "very agree": 5, "satisfied": 4}


def independent_stats(raw: pd.DataFrame) -> dict:
    cols = list(raw.columns)
    post = {"identify": cols[7], "describe": cols[8], "when": cols[9]}
    pre = {"identify": cols[10], "describe": cols[11], "when": cols[12]}
    num = lambda s: s.astype(str).str.replace("\xa0", " ").str.strip().str.lower().map(SCALE)
    out = {"rows": len(raw)}
    for k in post:
        out[f"% agree after {k}"] = (num(raw[post[k]]) >= 4).mean() * 100
        out[f"% agree before {k}"] = (num(raw[pre[k]]) >= 4).mean() * 100
        out[f"mean gain {k}"] = (num(raw[post[k]]) - num(raw[pre[k]])).mean()
    rec = pd.to_numeric(raw[cols[16]], errors="coerce").dropna()
    out["NPS"] = ((rec >= 9).mean() - (rec <= 6).mean()) * 100
    county = raw[cols[6]].astype(str).str.replace("\xa0", " ").str.strip().str.lower()
    out["Anne Arundel n"] = int((county == "anne arundel").sum())
    out["Prince George's n"] = int((county == "prince george's").sum())
    roles = raw[cols[4]].astype(str).str.strip().str.rstrip(";")
    out["Student-only n"] = int((roles == "Student").sum())
    return out


def pipeline_stats(df: pd.DataFrame) -> dict:
    ks = A.knowledge_summary(df).set_index("key")
    out = {"rows": len(df)}
    for k in ks.index:
        out[f"% agree after {k}"] = ks.loc[k, "% agree after"]
        out[f"% agree before {k}"] = ks.loc[k, "% agree before"]
        out[f"mean gain {k}"] = ks.loc[k, "Mean gain"]
    out["NPS"] = A.nps(df["recommend"])["nps"]
    out["Anne Arundel n"] = int((df["county"] == "Anne Arundel").sum())
    out["Prince George's n"] = int((df["county"] == "Prince George's").sum())
    out["Student-only n"] = int((df["role"] == "Student").sum())
    return out


def numeric_checks() -> bool:
    raw = pd.read_excel(RAW)
    df, _ = load_survey(RAW)  # all rows, no exclusions, so both sides see the same data
    ind, pipe = independent_stats(raw), pipeline_stats(df)
    rows, ok = [], True
    for k in ind:
        match = np.isclose(ind[k], pipe[k], atol=1e-6)
        ok &= bool(match)
        rows.append({"Statistic": k, "Independent": round(ind[k], 3), "Pipeline": round(pipe[k], 3),
                     "Match": "yes" if match else "NO"})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nAll numeric checks passed." if ok else "\nSome checks FAILED.")
    return ok


def build_theme_sample(n: int = 100, seed: int = 42) -> None:
    df, _ = load_survey(RAW)
    rows = []
    for col, book, nc, q in (("comment_valuable", T.VALUABLE_THEMES, False, "valuable"),
                             ("comment_improve", T.IMPROVE_THEMES, True, "improve")):
        s = df[["response_id", col]].dropna().sample(n // 2, random_state=seed)
        for rid, text in s.itertuples(index=False):
            rows.append({"response_id": rid, "question": q, "comment": T.redact(text),
                         "assigned_themes": " | ".join(T.code_comment(text, book, nc)),
                         "human_agrees (y/n/partial)": "", "human_theme_if_different": ""})
    SAMPLE.parent.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(SAMPLE, index=False)
    print(f"Wrote {len(rows)} comments to {SAMPLE}. Fill in the 'human_agrees' column, then run "
          "`python validate.py --score-themes`.")


def score_themes() -> None:
    # Teammates each fill their own copy (theme_sample_<name>.csv) to avoid merge
    # conflicts; a comment coded in several files counts once (first file wins).
    files = sorted(SAMPLE.parent.glob("theme_sample*.csv"))
    s = pd.concat([pd.read_csv(f).assign(source=f.name) for f in files], ignore_index=True)
    col = "human_agrees (y/n/partial)"
    done = s[s[col].notna() & (s[col].astype(str).str.strip() != "")]
    done = done.drop_duplicates(["response_id", "question"])
    print(f"Files read: {', '.join(f.name for f in files)}")
    s = s.drop_duplicates(["response_id", "question"])
    if done.empty:
        print("No rows have been hand-coded yet.")
        return
    v = done[col].astype(str).str.strip().str.lower().str[0]
    print(f"Hand-coded: {len(done)} of {len(s)}")
    print(f"  Full agreement:    {(v == 'y').mean() * 100:.0f}%")
    print(f"  Partial agreement: {(v == 'p').mean() * 100:.0f}%")
    print(f"  Disagreement:      {(v == 'n').mean() * 100:.0f}%")
    for q, g in done.groupby("question"):
        print(f"  {q}: {(g[col].astype(str).str.strip().str.lower().str[0] == 'y').mean() * 100:.0f}% full agreement (n={len(g)})")


if __name__ == "__main__":
    if "--score-themes" in sys.argv:
        score_themes()
    else:
        passed = numeric_checks()
        if not SAMPLE.exists():
            build_theme_sample()
        sys.exit(0 if passed else 1)
