"""Load and clean EveryMind 988 post-training survey exports.

The raw export (Microsoft Forms -> Excel) has long, slightly inconsistent column
headers, non-breaking spaces, free-text county names, multi-select roles and a few
off-scale Likert labels. `load_survey` turns that into one tidy row per response
plus a log of every cleaning step, so the numbers in the dashboard can be traced
back to the raw file.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Column matching
# ---------------------------------------------------------------------------
# Each canonical column is found by keywords (all must appear in the normalized
# header). This keeps the pipeline working if a future export tweaks wording,
# punctuation or column order.
COLUMN_RULES: Dict[str, List[str]] = {
    "response_id": ["^id$"],
    "start_time": ["start time"],
    "completion_time": ["completion time"],
    "language": ["^language$"],
    "role_raw": ["are you a"],
    "training_date": ["date of your training"],
    "county_raw": ["county"],
    "post_identify": ["agree with the statements", "identify"],
    "post_describe": ["agree with the statements", "describe 988"],
    "post_when": ["agree with the statements", "when to use 988"],
    "pre_identify": ["think back", "identify"],
    "pre_describe": ["think back", "describe 988"],
    "pre_when": ["think back", "when to use 988"],
    "presenter_engaged": ["aspects of the training", "engaged"],
    "presenter_knowledge": ["aspects of the training", "knew the subject"],
    "well_organized": ["aspects of the training", "well organized"],
    "recommend": ["likely are you to recommend"],
    "call_988": ["likely are you to call 988"],
    "comment_valuable": ["most valuable"],
    "comment_improve": ["improve this training"],
}

REQUIRED = [
    "post_identify", "post_describe", "post_when",
    "pre_identify", "pre_describe", "pre_when",
]

KNOWLEDGE_ITEMS = {
    "identify": "Identify mental health challenges & crises",
    "describe": "Describe 988 and how it works",
    "when": "Know when to use 988",
}
TRAINING_ITEMS = {
    "presenter_engaged": "Presenter engaged participants",
    "presenter_knowledge": "Presenter knew the subject",
    "well_organized": "Training was well organized",
}

# ---------------------------------------------------------------------------
# Value normalization
# ---------------------------------------------------------------------------
LIKERT = {
    "strongly disagree": 1,
    "disagree": 2,
    "neither agree nor disagree": 3,
    "neither agree or disagree": 3,
    "agree": 4,
    "strongly agree": 5,
    # Off-scale labels seen in the training-quality block. Treated as the
    # closest standard option; counts are reported in the cleaning log.
    "very agree": 5,
    "satisfied": 4,
}
LIKERT_LABELS = {1: "Strongly disagree", 2: "Disagree", 3: "Neutral", 4: "Agree", 5: "Strongly agree"}

COUNTY_CANONICAL = {
    "anne arundel": "Anne Arundel",
    "prince george's": "Prince George's",
    "montgomery": "Montgomery",
    "queen anne's": "Queen Anne's",
    "fairfax": "Fairfax (VA)",
}

ROLE_KEYS = {
    "Student": "student",
    "School staff member": "school staff",
    "Caregiver/parent": "caregiver",
    "Other (e.g., community member)": "other",
}


def norm_text(value) -> Optional[str]:
    """Unicode-normalize, drop invisible marks and collapse whitespace."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = unicodedata.normalize("NFKC", str(value))
    s = s.replace("‎", "").replace("‏", "").replace("﻿", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _match_columns(columns) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    normalized = {c: (norm_text(c) or "").lower() for c in columns}
    for canon, keys in COLUMN_RULES.items():
        for raw, low in normalized.items():
            if raw in mapping.values():
                continue
            if all(re.search(k, low) if k.startswith("^") else k in low for k in keys):
                mapping[canon] = raw
                break
    return mapping


def _county(value: Optional[str]) -> str:
    if not value:
        return "Unknown"
    low = value.lower().replace("county", "").strip()
    for key, canon in COUNTY_CANONICAL.items():
        if low.startswith(key):
            return canon
    return "Other / out of area"


def _likert(value) -> Optional[int]:
    s = norm_text(value)
    return LIKERT.get(s.lower()) if s else None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
@dataclass
class CleaningReport:
    raw_rows: int = 0
    steps: List[Dict[str, object]] = field(default_factory=list)
    unmatched_columns: List[str] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)

    def add(self, step: str, rows: int, detail: str = "") -> None:
        self.steps.append({"Step": step, "Rows affected": int(rows), "Detail": detail})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.steps, columns=["Step", "Rows affected", "Detail"])


def load_raw(source) -> pd.DataFrame:
    """Read an .xlsx/.csv path or uploaded file object."""
    name = getattr(source, "name", str(source)).lower()
    if name.endswith(".csv"):
        return pd.read_csv(source)
    return pd.read_excel(source)


def clean_survey(raw: pd.DataFrame):
    """Return (clean DataFrame, CleaningReport)."""
    rep = CleaningReport(raw_rows=len(raw))
    mapping = _match_columns(raw.columns)
    rep.missing_columns = [c for c in COLUMN_RULES if c not in mapping]
    rep.unmatched_columns = [c for c in raw.columns if c not in mapping.values()]
    missing_required = [c for c in REQUIRED if c not in mapping]
    if missing_required:
        raise ValueError(
            "Could not find the pre/post knowledge questions in this file: "
            + ", ".join(missing_required)
        )

    df = pd.DataFrame({canon: raw[col] for canon, col in mapping.items()})
    for canon in COLUMN_RULES:
        if canon not in df:
            df[canon] = pd.NA
    if df["response_id"].isna().all():
        df["response_id"] = range(1, len(df) + 1)

    # --- language -----------------------------------------------------------
    lang = df["language"].map(norm_text).fillna("")
    df["language"] = lang.map(
        lambda s: "Spanish" if s.lower().startswith(("espa", "spanish")) else ("English" if s else "Unknown")
    )

    # --- county -------------------------------------------------------------
    county_text = df["county_raw"].map(norm_text)
    df["county"] = county_text.map(_county)
    changed = (county_text.fillna("") != df["county"]).sum()
    rep.add("Standardize county names", changed,
            f"{county_text.nunique()} raw spellings -> {df['county'].nunique()} counties")

    # --- roles (multi-select, ';'-separated) --------------------------------
    role_text = df["role_raw"].map(norm_text).fillna("")
    for key in ROLE_KEYS.values():
        df[f"is_{key.split()[0]}"] = role_text.str.lower().str.contains(key, regex=False)
    flags = df[[f"is_{k.split()[0]}" for k in ROLE_KEYS.values()]]
    n_roles = flags.sum(axis=1)
    labels = list(ROLE_KEYS.keys())
    df["role"] = [
        labels[list(row).index(True)] if n == 1 else ("Multiple roles" if n > 1 else "Not reported")
        for row, n in zip(flags.values, n_roles)
    ]
    df.loc[df["role"] == "Other (e.g., community member)", "role"] = "Community member / other"
    df["role_group"] = df["role"].where(df["role"] == "Student", "Adult (staff, caregiver, community)")
    df.loc[df["role"] == "Not reported", "role_group"] = "Not reported"
    rep.add("Split multi-select roles", (n_roles > 1).sum(), "respondents selecting 2+ roles -> 'Multiple roles'")

    # --- dates --------------------------------------------------------------
    df["start_time"] = pd.to_datetime(df["start_time"], errors="coerce")
    df["completion_time"] = pd.to_datetime(df["completion_time"], errors="coerce")
    td = pd.to_datetime(df["training_date"], errors="coerce")
    missing_td = td.isna() & df["start_time"].notna()
    td = td.fillna(df["start_time"].dt.normalize())
    df["training_date"] = td
    df["training_month"] = td.dt.to_period("M").dt.to_timestamp()
    rep.add("Fill missing training date from submission date", missing_td.sum())
    df["session_id"] = df["county"] + " | " + td.dt.strftime("%Y-%m-%d").fillna("unknown")

    # --- Likert -> 1..5 -----------------------------------------------------
    off_scale = 0
    for col in ["post_identify", "post_describe", "post_when",
                "pre_identify", "pre_describe", "pre_when", *TRAINING_ITEMS]:
        txt = df[col].map(norm_text)
        off_scale += txt.fillna("").str.lower().isin(["very agree", "satisfied"]).sum()
        df[col] = txt.map(_likert).astype("Float64")
    rep.add("Map off-scale labels ('Very agree'->5, 'Satisfied'->4)", off_scale,
            "cells, training-quality questions only")

    for k in KNOWLEDGE_ITEMS:
        df[f"gain_{k}"] = df[f"post_{k}"] - df[f"pre_{k}"]
    df["post_mean"] = df[[f"post_{k}" for k in KNOWLEDGE_ITEMS]].mean(axis=1)
    df["pre_mean"] = df[[f"pre_{k}" for k in KNOWLEDGE_ITEMS]].mean(axis=1)
    df["gain_mean"] = df["post_mean"] - df["pre_mean"]

    for col in ["recommend", "call_988"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")
        df.loc[(df[col] < 0) | (df[col] > 10), col] = pd.NA
    rep.add("'Likely to call 988' not asked / blank", df["call_988"].isna().sum(),
            "question appears only on some survey versions; analysed on its own n")

    for col in ["comment_valuable", "comment_improve"]:
        df[col] = df[col].map(norm_text)

    # --- quality flags (kept in data, excluded by default in analysis) ------
    post_cols = [f"post_{k}" for k in KNOWLEDGE_ITEMS]
    all_sd_post = (df[post_cols] == 1).all(axis=1)
    positive_elsewhere = (df[list(TRAINING_ITEMS)] >= 4).any(axis=1) | (df["recommend"] >= 8)
    df["flag_scale_misread"] = (all_sd_post & positive_elsewhere.fillna(False)).astype(bool)
    rep.add("Flag likely scale misread", df["flag_scale_misread"].sum(),
            "'Strongly disagree' on every post item but positive presenter/recommend ratings")

    dur = (df["completion_time"] - df["start_time"]).dt.total_seconds()
    df["duration_sec"] = dur
    df["flag_speeder"] = (dur < 15).fillna(False).astype(bool)
    rep.add("Flag very fast completions (<15 s)", df["flag_speeder"].sum())

    content = [c for c in COLUMN_RULES if c not in ("response_id", "start_time", "completion_time")]
    df["flag_duplicate"] = df[content].astype(str).duplicated(keep="first")
    rep.add("Flag exact duplicate submissions", df["flag_duplicate"].sum(), "first copy kept")

    df["flag_any"] = df[["flag_scale_misread", "flag_speeder", "flag_duplicate"]].any(axis=1)
    rep.add("Total responses flagged", df["flag_any"].sum(),
            "excluded by default; toggle in dashboard")
    return df.drop(columns=["county_raw"]), rep


def load_survey(source):
    return clean_survey(load_raw(source))
