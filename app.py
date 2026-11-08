"""EveryMind 988 Training Insights dashboard.

Run:  streamlit run app.py
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from everymind import analysis as A
from everymind import themes as T
from everymind.cleaning import KNOWLEDGE_ITEMS, clean_survey, load_raw

DEFAULT_DATA = Path(__file__).parent / "data" / "survey.xlsx"

BEFORE, AFTER = "#9AA5B1", "#0F766E"
LIKERT_COLORS = {1: "#B91C1C", 2: "#F87171", 3: "#D1D5DB", 4: "#5EEAD4", 5: "#0F766E"}
LIKERT_NAMES = {1: "Strongly disagree", 2: "Disagree", 3: "Neutral", 4: "Agree", 5: "Strongly agree"}
EVIDENCE_COLORS = {"Strong": "#0F766E", "Significant, small effect": "#5EEAD4",
                   "Significant but thin (n<30)": "#F59E0B", "Not significant": "#D1D5DB"}

st.set_page_config(page_title="988 Training Insights", page_icon="📞", layout="wide")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Cleaning survey data…")
def load(data: bytes, name: str):
    buf = io.BytesIO(data)
    buf.name = name
    df, rep = clean_survey(load_raw(buf))
    return df, rep.to_frame(), rep.missing_columns, rep.raw_rows


@st.cache_data(show_spinner="Coding open-ended comments…")
def coded_comments(df: pd.DataFrame) -> pd.DataFrame:
    return T.code_comments(df)


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def suppressed_note(tbl: pd.DataFrame, min_n: int):
    hidden = tbl[tbl["Reliability"] == "Suppressed"]
    if len(hidden):
        st.caption(f"🔒 {len(hidden)} group(s) with fewer than {min_n} responses are hidden "
                   f"({', '.join(map(str, hidden['Group']))}) to protect privacy and avoid unreliable numbers.")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📞 988 Training Insights")
st.sidebar.caption("EveryMind post-training survey dashboard")
upload = st.sidebar.file_uploader("Upload a new survey export (.xlsx or .csv)", type=["xlsx", "csv"])
if upload is not None:
    raw_bytes, raw_name = upload.getvalue(), upload.name
elif DEFAULT_DATA.exists():
    raw_bytes, raw_name = DEFAULT_DATA.read_bytes(), DEFAULT_DATA.name
else:
    st.info("Upload a survey export to begin.")
    st.stop()

try:
    df_all, clean_log, missing_cols, raw_rows = load(raw_bytes, raw_name)
except ValueError as e:
    st.error(f"This file doesn't look like the 988 post-training survey: {e}")
    st.stop()

st.sidebar.caption(f"Source: **{raw_name}** · {raw_rows:,} rows")
st.sidebar.divider()
st.sidebar.subheader("Filters")
counties = st.sidebar.multiselect("County", sorted(df_all["county"].unique()))
roles = st.sidebar.multiselect("Role", sorted(df_all["role"].unique()))
languages = st.sidebar.multiselect("Survey language", sorted(df_all["language"].unique()))
dmin, dmax = df_all["training_date"].min().date(), df_all["training_date"].max().date()
date_range = st.sidebar.date_input("Training date range", (dmin, dmax), min_value=dmin, max_value=dmax)
if not isinstance(date_range, (tuple, list)) or len(date_range) != 2:
    date_range = (dmin, dmax)

st.sidebar.divider()
st.sidebar.subheader("Settings")
min_n = st.sidebar.slider("Minimum group size to report", 5, 30, A.DEFAULT_MIN_N,
                          help="Groups smaller than this are hidden. Groups under 30 are marked low-confidence.")
exclude_flagged = st.sidebar.toggle("Exclude flagged responses", value=True,
                                    help="Likely scale misreads, duplicates and <15-second completions. See Data Quality tab.")

df = A.apply_filters(df_all, exclude_flagged, counties, roles, languages, date_range)
if len(df) == 0:
    st.warning("No responses match these filters.")
    st.stop()
if len(df) < min_n:
    st.warning(f"Only {len(df)} responses match these filters, which is below the minimum group size of {min_n}. "
               "Results are hidden to protect respondent privacy.")
    st.stop()

# ---------------------------------------------------------------------------
# Shared computations
# ---------------------------------------------------------------------------
ks = A.knowledge_summary(df)
tq = A.training_quality(df)
rec = A.nps(df["recommend"])
call = df["call_988"].astype(float).dropna()

st.title("988 Awareness Training: What Participants Tell Us")
active = [f for f, v in (("county", counties), ("role", roles), ("language", languages)) if v]
st.caption(f"{len(df):,} responses · training dates {pd.Timestamp(date_range[0]):%b %d, %Y} – "
           f"{pd.Timestamp(date_range[1]):%b %d, %Y}" + (f" · filtered by {', '.join(active)}" if active else "")
           + (" · flagged responses excluded" if exclude_flagged else " · flagged responses included"))

tabs = st.tabs(["Overview", "Knowledge gains", "Group gaps", "Trends & sessions", "Comments",
                "Data quality", "Export"])

# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
with tabs[0]:
    when = ks.set_index("key").loc["when"]
    describe = ks.set_index("key").loc["describe"]
    c = st.columns(5)
    c[0].metric("Responses", f"{len(df):,}")
    c[1].metric("Know when to use 988 (after)", f"{when['% agree after']:.0f}%",
                f"{when['% agree after'] - when['% agree before']:+.0f} pts vs. before")
    c[2].metric("Can describe 988 (after)", f"{describe['% agree after']:.0f}%",
                f"{describe['% agree after'] - describe['% agree before']:+.0f} pts vs. before")
    c[3].metric("Net Promoter Score", f"{rec['nps']:+.0f}" if rec["n"] else "–",
                help=f"% rating 9–10 minus % rating 0–6 (n={rec['n']}). Ranges from −100 to +100.")
    c[4].metric("Likely to call 988", f"{call.mean():.1f} / 10" if len(call) >= min_n else "–",
                help=f"Asked on some survey versions only (n={len(call)}).")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Confidence before vs. after training")
        st.caption("% who agree or strongly agree. 'Before' is a retrospective self-rating given after the training.")
        fig = go.Figure()
        for _, r in ks.iterrows():
            fig.add_trace(go.Scatter(x=[r["% agree before"], r["% agree after"]], y=[r["Item"]] * 2, mode="lines",
                                     line=dict(color="#CBD2D9", width=6), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=ks["% agree before"], y=ks["Item"], mode="markers+text", name="Before",
                                 marker=dict(color=BEFORE, size=16), text=ks["% agree before"].round(0).astype(int).astype(str) + "%",
                                 textposition="middle left", textfont=dict(color="#52606D")))
        fig.add_trace(go.Scatter(x=ks["% agree after"], y=ks["Item"], mode="markers+text", name="After",
                                 marker=dict(color=AFTER, size=16), text=ks["% agree after"].round(0).astype(int).astype(str) + "%",
                                 textposition="middle right", textfont=dict(color=AFTER)))
        fig.update_layout(xaxis=dict(range=[0, 108], title="% agree", ticksuffix="%"), yaxis=dict(title=None),
                          height=300, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig)
    with right:
        st.subheader("Training delivery")
        st.caption("% agree or strongly agree")
        fig = px.bar(tq, x="% agree", y="Item", orientation="h", text=tq["% agree"].round(0).astype(int).astype(str) + "%",
                     color_discrete_sequence=[AFTER], hover_data={"n": True})
        fig.update_layout(xaxis=dict(range=[0, 100], ticksuffix="%"), yaxis_title=None, height=300,
                          margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig)

    st.subheader("Where to look first")
    gaps = A.gap_finder(df, ["county", "role_group", "language"], min_n=min_n)
    top = gaps[(gaps["Direction"] == "Lower") & (gaps["Evidence"] != "Not significant")].head(5) if len(gaps) else gaps
    if len(top):
        for _, r in top.iterrows():
            icon = "⚠️" if r["Evidence"] == "Significant but thin (n<30)" else "🔻"
            st.markdown(f"{icon} {r['Finding']} *Evidence: {r['Evidence'].lower()}, adjusted p={fmt_p(r['p (BH-adjusted)'])}.*")
    else:
        st.markdown("No group scores significantly lower than the rest with the current filters.")
    still = ks.sort_values("% still not confident", ascending=False).iloc[0]
    st.markdown(f"📌 After training, **{still['% still not confident']:.0f}%** of participants still do not agree they can "
                f"*{still['Item'].lower()}*. This is the weakest of the three learning goals.")

# ---------------------------------------------------------------------------
# Knowledge gains
# ---------------------------------------------------------------------------
with tabs[1]:
    st.subheader("How ratings shifted on each learning goal")
    dist = A.likert_distribution(df)
    dist["Label"] = dist["Item"] + " — " + dist["When"]
    fig = go.Figure()
    order = []
    for item in KNOWLEDGE_ITEMS.values():
        order += [f"{item} — After", f"{item} — Before"]
    for score in [2, 1, 3, 4, 5]:
        sub = dist[dist["Rating"] == score].set_index("Label").reindex(order)
        x = -sub["Percent"] if score < 3 else (sub["Percent"] / 2 if score == 3 else sub["Percent"])
        fig.add_trace(go.Bar(y=order, x=x, orientation="h", name=LIKERT_NAMES[score], marker_color=LIKERT_COLORS[score],
                             customdata=sub["Percent"], hovertemplate="%{y}<br>" + LIKERT_NAMES[score] + ": %{customdata:.1f}%<extra></extra>"))
        if score == 3:
            fig.add_trace(go.Bar(y=order, x=-sub["Percent"] / 2, orientation="h", marker_color=LIKERT_COLORS[3],
                                 showlegend=False, customdata=sub["Percent"],
                                 hovertemplate="%{y}<br>Neutral: %{customdata:.1f}%<extra></extra>"))
    fig.update_layout(barmode="relative", height=430, xaxis=dict(title="% of responses (disagree ← | → agree)", ticksuffix="%"),
                      yaxis=dict(autorange="reversed", title=None), legend=dict(orientation="h", y=-0.2, traceorder="normal"),
                      margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig)

    show = ks.drop(columns=["key"]).copy()
    show["95% CI of gain"] = show.apply(lambda r: f"{r['Gain CI low']:.2f} – {r['Gain CI high']:.2f}", axis=1)
    show["Wilcoxon p"] = show["Wilcoxon p"].map(fmt_p)
    st.dataframe(show[["Item", "n", "Pre mean", "Post mean", "Mean gain", "95% CI of gain", "% agree before", "% agree after",
                       "% improved", "% no change", "% declined", "% at ceiling before", "Wilcoxon p",
                       "Effect size (rank-biserial)"]].round(2), hide_index=True, width="stretch")
    with st.expander("How to read this / method notes"):
        st.markdown(
            "- Ratings are scored 1 (Strongly disagree) to 5 (Strongly agree). **Gain** = after minus before for the same person.\n"
            "- Significance uses the **Wilcoxon signed-rank test**, which suits ordinal Likert data and paired responses. "
            "Effect size is the matched-pairs rank-biserial correlation (−1 to 1; above 0.5 is large).\n"
            "- **Retrospective pre-ratings**: 'before' is recalled *after* the session. This avoids the problem of people "
            "not knowing what they didn't know, but it can exaggerate gains (people want to show the training worked). "
            "Treat gains as self-reported change, not measured learning.\n"
            "- **Ceiling**: people who already rated 'Strongly agree' before cannot show a gain, so % improved understates "
            "impact for high-knowledge groups.")

# ---------------------------------------------------------------------------
# Group gaps
# ---------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Do outcomes differ across communities and participant groups?")
    cc = st.columns([2, 2, 3])
    dim = cc[0].selectbox("Compare by", list(A.GROUP_DIMENSIONS), format_func=A.GROUP_DIMENSIONS.get)
    metric = cc[1].selectbox("Outcome", ["Mean gain", "Post mean", "% know when to use 988", "NPS",
                                         "Likely to call 988 (0-10)"])
    students_only = cc[2].toggle("Students only (removes the effect of audience mix)", value=False,
                                 help="Most Anne Arundel respondents are students, and students rate differently from adults. "
                                      "Turn this on to compare counties among students only.")
    gdf = df[df["role"] == "Student"] if students_only else df
    gs = A.group_summary(gdf, dim, min_n)
    vis = gs[gs["Reliability"] != "Suppressed"].dropna(subset=[metric])
    if len(vis):
        ci = {"Mean gain": ("Gain CI low", "Gain CI high"), "% know when to use 988": ("CI low %", "CI high %")}.get(metric)
        groups = vis["Group"].astype(str)
        fig = go.Figure(go.Bar(
            x=vis[metric], y=groups, orientation="h",
            marker_color=[AFTER if r == "OK" else "#F59E0B" for r in vis["Reliability"]],
            error_x=dict(type="data", symmetric=False, array=vis[ci[1]] - vis[metric], arrayminus=vis[metric] - vis[ci[0]],
                         color="#52606D") if ci else None,
            customdata=vis["n"], hovertemplate="%{y}: %{x:.2f} (n=%{customdata})<extra></extra>", showlegend=False))
        # Labels sit past the end of the whisker (or past zero for negative bars) so they never overlap it.
        right_edge = (vis[ci[1]] if ci else vis[metric]).clip(lower=0)
        span = max(float(right_edge.max()), float(vis[metric].abs().max()), 1e-9)
        fig.add_trace(go.Scatter(
            x=right_edge + span * 0.02, y=groups, mode="text", textposition="middle right", hoverinfo="skip",
            text=[f"<b>{v:.2f}</b>" if abs(v) < 10 else f"<b>{v:.0f}</b>" for v in vis[metric]],
            textfont=dict(color="#1F2933"), showlegend=False))
        x_lo = min(0.0, float(vis[metric].min()) * 1.15)
        fig.update_layout(height=80 + 50 * len(vis), yaxis=dict(autorange="reversed", title=None),
                          xaxis=dict(title=metric, range=[x_lo, span * 1.15]), margin=dict(l=10, r=20, t=10, b=10))
        st.plotly_chart(fig)
        st.caption("Teal = n ≥ 30. Amber = low confidence (n < 30). Whiskers = 95% confidence interval where shown.")
    suppressed_note(gs, min_n)
    st.dataframe(gs.round(2), hide_index=True, width="stretch")

    st.subheader("Gap finder")
    st.caption("Each group is compared with everyone else (Mann-Whitney U test). p-values are adjusted for running many "
               "tests (Benjamini-Hochberg), so a 'significant' gap is unlikely to be chance. Thin findings are labelled.")
    gap = A.gap_finder(gdf, ["county", "role", "language"] if not students_only else ["county", "language"], min_n=min_n)
    if len(gap):
        ev = st.multiselect("Show evidence levels", list(EVIDENCE_COLORS), default=list(EVIDENCE_COLORS)[:3])
        g = gap[gap["Evidence"].isin(ev)].copy()
        g["p (BH-adjusted)"] = g["p (BH-adjusted)"].map(fmt_p)
        st.dataframe(g[["Finding", "Evidence", "Group mean", "Rest mean", "Difference", "Effect size", "p (BH-adjusted)",
                        "Group n"]].round(2), hide_index=True, width="stretch")
    else:
        st.info("Not enough data in the current filter to compare groups.")

# ---------------------------------------------------------------------------
# Trends & sessions
# ---------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Outcomes over time")
    tr = A.monthly_trend(df, min_n)
    tm = st.radio("Measure", ["Post mean", "Mean gain", "NPS"], horizontal=True)
    fig = go.Figure()
    # Bars go on the base axis and the line on the overlaying axis: Plotly draws overlaying-axis traces on top.
    fig.add_trace(go.Bar(x=tr["Month"], y=tr["n"], name="Responses", marker_color="#E4E7EB", opacity=0.7,
                         hovertemplate="%{x|%b %Y}: n=%{y}<extra></extra>"))
    fig.add_trace(go.Scatter(x=tr["Month"], y=tr[tm], name=tm, mode="lines+markers", line=dict(color=AFTER, width=3),
                             marker=dict(size=9), connectgaps=False, yaxis="y2",
                             hovertemplate="%{x|%b %Y}: %{y:.2f}<extra></extra>"))
    fig.update_layout(height=380, yaxis=dict(title="Responses", side="right", showgrid=False),
                      yaxis2=dict(title=tm, overlaying="y", side="left", showgrid=True, gridcolor="#EEF1F4"),
                      legend=dict(orientation="h", y=-0.2), margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig)
    st.caption(f"Months with fewer than {min_n} responses are left blank. Grey bars show how many responses each month has.")

    st.subheader("Sessions to review")
    st.caption("A session = one county on one training date. Flagged when post-training confidence, presenter engagement "
               "or NPS is more than one standard deviation below the average session.")
    ses = A.session_review(df, min_n)
    only_flag = st.toggle("Show only flagged sessions", value=False)
    if only_flag:
        ses = ses[ses["Review"] != ""]
    ses_show = ses.drop(columns=["session_id"]).copy()
    ses_show["Training date"] = pd.to_datetime(ses_show["Training date"]).dt.date
    st.dataframe(ses_show.round(2), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------
with tabs[4]:
    coded = coded_comments(df)
    q = st.radio("Question", ["Most valuable thing learned", "How to improve / questions"], horizontal=True)
    col = "comment_valuable" if q.startswith("Most") else "comment_improve"
    n_com = int(df[col].notna().sum())
    counts = T.theme_counts(coded, q, n_com)
    st.caption(f"{n_com:,} comments. A comment can match several themes. Themes come from a transparent keyword codebook "
               "(English + Spanish) checked by hand on a random sample.")
    left, right = st.columns([3, 2])
    with left:
        plot = counts[counts["Theme"] != "Uncoded / other"]
        fig = px.bar(plot, x="% of comments", y="Theme", orientation="h", text=plot["Comments"],
                     color_discrete_sequence=[AFTER])
        fig.update_layout(height=60 + 32 * len(plot), yaxis=dict(autorange="reversed", title=None),
                          xaxis_ticksuffix="%", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig)
        unc = counts[counts["Theme"] == "Uncoded / other"]
        if len(unc):
            st.caption(f"{int(unc['Comments'].iloc[0])} comments ({unc['% of comments'].iloc[0]:.0f}%) didn't match any theme. "
                       "Browse them on the right.")
    with right:
        theme = st.selectbox("Read comments for theme", counts["Theme"].tolist())
        sub = coded[(coded["Question"] == q) & (coded["Theme"] == theme)]
        grp = st.radio("From", ["Everyone", "Students", "Adults"], horizontal=True, key="cgrp")
        if grp != "Everyone":
            sub = sub[(sub["role_group"] == "Student") == (grp == "Students")]
        st.caption(f"{len(sub)} comments · emails and phone numbers removed")
        st.dataframe(sub[["Comment"]].drop_duplicates().head(200), hide_index=True, width="stretch", height=420)

    if col == "comment_improve":
        qs = coded[(coded["Question"] == q) & coded["Is question"]].drop_duplicates("response_id")
        st.info(f"💡 **{len(qs)} of {n_com} 'improve' answers ({100 * len(qs) / max(n_com, 1):.0f}%) are questions about 988** "
                "(confidentiality, police involvement, how texting works, who answers). These are content gaps the "
                "training could answer up front, for example with an FAQ slide.")

    st.subheader("Themes by audience")
    by = coded[coded["Question"] == q].drop_duplicates(["response_id", "Theme"])
    denom = df[df[col].notna()].groupby("role_group").size()
    cross = (by.groupby(["Theme", "role_group"]).size() / denom).mul(100).rename("% of group's comments").reset_index()
    cross = cross[cross["role_group"].isin(denom[denom >= min_n].index) & (cross["Theme"] != "Uncoded / other")]
    fig = px.bar(cross, x="% of group's comments", y="Theme", color="role_group", barmode="group", orientation="h",
                 color_discrete_sequence=[AFTER, "#F59E0B", BEFORE])
    fig.update_layout(height=80 + 40 * cross["Theme"].nunique(), yaxis=dict(title=None, autorange="reversed"),
                      xaxis_ticksuffix="%", legend=dict(orientation="h", y=-0.15, title=None), margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig)

# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------
with tabs[5]:
    st.subheader("What the cleaning step did")
    st.dataframe(clean_log, hide_index=True, width="stretch")
    if missing_cols:
        st.warning("These expected questions were not found in the uploaded file, so related charts are empty: "
                   + ", ".join(missing_cols))
    c = st.columns(3)
    c[0].metric("Raw rows", f"{raw_rows:,}")
    c[1].metric("Flagged", f"{int(df_all['flag_any'].sum())}")
    c[2].metric("Used in analysis (before filters)", f"{int((~df_all['flag_any']).sum()) if exclude_flagged else len(df_all):,}")

    st.subheader("Answers missing, by question")
    miss_cols = {"Presenter engaged": "presenter_engaged", "Presenter knew subject": "presenter_knowledge",
                 "Well organized": "well_organized", "Likely to recommend": "recommend", "Likely to call 988": "call_988",
                 "Most valuable comment": "comment_valuable", "Improve comment": "comment_improve"}
    miss = pd.DataFrame({"Question": list(miss_cols),
                         "% missing": [100 * df_all[c].isna().mean() for c in miss_cols.values()]})
    fig = px.bar(miss, x="% missing", y="Question", orientation="h", text=miss["% missing"].round(0).astype(int).astype(str) + "%",
                 color_discrete_sequence=[BEFORE])
    fig.update_layout(height=320, xaxis=dict(range=[0, 100], ticksuffix="%"), yaxis_title=None, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig)
    st.caption("'Likely to call 988' only appears on some survey versions. Make it required on every version to track "
               "behavioral intent consistently.")

    st.subheader("Flagged responses")
    fl = df_all[df_all["flag_any"]]
    reason = np.select([fl["flag_scale_misread"], fl["flag_duplicate"], fl["flag_speeder"]],
                       ["Likely scale misread", "Duplicate", "Completed in <15 s"], "")
    st.dataframe(pd.DataFrame({"Response ID": fl["response_id"], "Reason": reason, "County": fl["county"],
                               "Language": fl["language"], "Post ratings": fl["post_mean"].round(2),
                               "Presenter engaged": fl["presenter_engaged"], "Recommend": fl["recommend"]}),
                 hide_index=True, width="stretch")
    st.caption("Likely scale misread: chose 'Strongly disagree' on every post-training knowledge item while rating the "
               "presenter or the recommendation question positively. This usually means the respondent read the scale backwards.")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
with tabs[6]:
    st.subheader("Download results")
    st.caption("All tables reflect the current filters and settings. Suppressed groups are removed. Comments have emails and "
               "phone numbers removed. No names or other identifiers are included.")

    def build_excel() -> bytes:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as xw:
            pd.DataFrame({"Setting": ["Source file", "Responses analysed", "Flagged excluded", "Minimum group size",
                                      "County filter", "Role filter", "Language filter", "Date range"],
                          "Value": [raw_name, len(df), exclude_flagged, min_n, ", ".join(counties) or "All",
                                    ", ".join(roles) or "All", ", ".join(languages) or "All",
                                    f"{date_range[0]} to {date_range[1]}"]}).to_excel(xw, sheet_name="About", index=False)
            ks.drop(columns=["key"]).to_excel(xw, sheet_name="Knowledge gains", index=False)
            tq.to_excel(xw, sheet_name="Training delivery", index=False)
            for d, label in A.GROUP_DIMENSIONS.items():
                g = A.group_summary(df, d, min_n)
                g[g["Reliability"] != "Suppressed"].to_excel(xw, sheet_name=f"By {label}"[:31], index=False)
            A.gap_finder(df, min_n=min_n).to_excel(xw, sheet_name="Gap finder", index=False)
            A.monthly_trend(df, min_n).to_excel(xw, sheet_name="Monthly trend", index=False)
            A.session_review(df, min_n).to_excel(xw, sheet_name="Sessions", index=False)
            cc_ = coded_comments(df)
            for qq, cl, sheet in (("Most valuable thing learned", "comment_valuable", "Themes - valuable"),
                                  ("How to improve / questions", "comment_improve", "Themes - improve")):
                T.theme_counts(cc_, qq, int(df[cl].notna().sum())).to_excel(xw, sheet_name=sheet, index=False)
            clean_log.to_excel(xw, sheet_name="Cleaning log", index=False)
        return out.getvalue()

    st.download_button("⬇️ Summary workbook (.xlsx)", build_excel(), file_name="988_training_summary.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    clean_cols = ["response_id", "training_date", "county", "role", "role_group", "language",
                  *[f"{w}_{k}" for k in KNOWLEDGE_ITEMS for w in ("pre", "post")], "presenter_engaged",
                  "presenter_knowledge", "well_organized", "recommend", "call_988", "flag_any"]
    st.download_button("⬇️ Cleaned response data (.csv, no comments)", df[clean_cols].to_csv(index=False).encode(),
                       file_name="988_cleaned_responses.csv", mime="text/csv")
