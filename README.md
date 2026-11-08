# 988 Training Insights

A dashboard that turns EveryMind's Understanding 988 post-training survey export into findings staff can act on: knowledge gains, gaps between participant groups, trends over time, sessions to review, and themes in open-ended comments.

## Run it

Requires Python 3.9+.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501 and loads the bundled dataset (`data/survey.xlsx`).

## Use it on a new survey

1. Export responses from Microsoft Forms to Excel.
2. In the dashboard sidebar, use **Upload a new survey export** (`.xlsx` or `.csv`).
3. The cleaning step runs automatically. Check the **Data quality** tab for what was fixed or flagged.
4. Use the filters (county, role, language, dates) and the **Export** tab to download a summary workbook for reports and grant applications.

Columns are matched by keywords in the question text, not by exact headers or position, so small wording changes in future exports still load. If a required question is missing, the app says which one.

**Who / how often:** a program coordinator, after each batch of trainings or monthly. No coding needed once the app is running. It can also be hosted online (for example on Streamlit Community Cloud) so staff only need a link.

## What's inside

| Path | Purpose |
|---|---|
| `app.py` | Streamlit dashboard (frontend) |
| `everymind/cleaning.py` | Column matching, label standardization, county/role cleanup, quality flags, cleaning log |
| `everymind/analysis.py` | Pre/post gains (Wilcoxon), group summaries with confidence intervals, gap finder (Mann-Whitney + Benjamini-Hochberg), NPS, trends, session review |
| `everymind/themes.py` | Editable keyword codebook (English + Spanish) for open-ended comments, plus PII redaction |
| `validate.py` | Recomputes headline numbers independently from the raw file and checks they match. Also builds and scores a hand-coded sample for the comment themes |
| `AI_LOG.md` | How AI tools were used and checked |

## Method notes

- **Scoring:** Likert answers are scored 1–5. "Agree" means a 4 or 5. Off-scale labels ("Very agree" → 5, "Satisfied" → 4) appear only in the training-quality items.
- **Pre/post:** the "before" ratings are retrospective, collected after the training. Gains are self-reported change, not measured learning.
- **Small groups:** groups under the minimum size (default 10, adjustable) are hidden. Groups under 30 are labeled low-confidence.
- **Flagged responses** are excluded by default and can be included with a toggle. They are: likely scale misreads, exact duplicates, and completions under 15 seconds.
- **Audience mix:** students make up about 83% of responses and rate the training differently from adults. Use the "Students only" toggle on the Group gaps tab to compare counties fairly.
- **Privacy:** comments have emails and phone numbers removed before display or export. The exports contain no names.

## Validate

```bash
python validate.py                 # numeric cross-check
python validate.py --score-themes  # after hand-coding validation/theme_sample.csv
```
