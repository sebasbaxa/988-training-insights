# AI Process Log

Working notes for the AI Process Appendix. Tool: Claude Code (Claude Opus 5.5), used as a coding and analysis assistant.

## Prompts

**P1. Build kickoff**
> "Lets start with your suggestions for the project, as a techstack I want have a python backend and then like you said a steamlit frontend is fine."

Result: Claude proposed a Streamlit dashboard with a Python analysis package (`everymind/`). It covers cleaning, pre/post gains, group-gap analysis with small-group suppression, and offline comment theming.

**P2. Human visual review → fix request**
> "In the group gaps tab the graph is overlapped with the numbers, and in the trends and sessions the responses bar is hiding the post mean line"

Result: two chart-layout fixes (see E5).

## AI-assisted decisions (and how they were checked)

| # | What the AI did | Validation / human decision |
|---|---|---|
| D1 | Profiled the raw export. Found 15 county spellings, non-breaking spaces in labels, off-scale labels ("Very agree", "Satisfied"), multi-select roles split by `;`, and the "likely to call 988" item missing for 1,006/1,299 rows | Spot-checked counts directly in the spreadsheet |
| D2 | Mapped "Very agree" → Strongly agree (5) and "Satisfied" → Agree (4) | Judgment call: only 68 cells, all in training-quality items. Logged in the cleaning report |
| D3 | Found 31 respondents who chose "Strongly disagree" on every post-training item. Many of them still rated the presenter highly and the training 9–10 to recommend. The AI suggested this was a likely scale misread | Narrowed to 19 rows that also have a positive presenter or recommend signal. Flagged rather than deleted; excluded by default, with a toggle to include them |
| D4 | Used keyword-based column matching instead of fixed headers, so future exports still load | Tested on the provided file: all 20 columns matched |
| D5 | Chose Wilcoxon signed-rank for pre/post (paired, ordinal) and Mann-Whitney U with Benjamini-Hochberg correction for group gaps. Groups below n=10 are suppressed; groups below 30 are labeled "thin" | Standard non-parametric choices for Likert data. The multiple-testing correction is needed because the gap finder runs about 50 tests |
| D6 | The gap finder showed Anne Arundel far below other counties on recommend score. The AI noticed Anne Arundel is mostly students, and students score lower everywhere, so the county gap is mixed up with role (a confound) | Added a "Students only" toggle so counties can be compared within one audience |
| D7 | While reading comments, found that about a third of "How can we improve" answers are actually *questions* about 988 (police involvement, confidentiality, texting, who answers) | Read 110 random comments to confirm. Added question-type themes and an "is question" flag |
| D8 | Built an offline keyword codebook (English + Spanish) for comment themes instead of calling an LLM API, so judges and staff can run it with no API key and every theme rule can be read and edited | Accuracy is checked by a hand-coded random sample of 100 comments (`validation/theme_sample.csv`) |

## AI errors / limitations encountered

- **E1. Theme over-count from a regex bug.** The first codebook's "Statistics and facts" rule matched any 2+ digit number, so it also matched "988" itself. That inflated the theme to **46% of comments**. Caught by reading the coded output. A second fix was needed because "24/7" and "365" also matched. After the fix the theme covers about 2% of comments.
- **E2. Coverage gaps in the first codebook.** About 41% of "most valuable" comments were uncoded at first. We reviewed samples of uncoded comments, added patterns (e.g. "even minors can call", "reasons to call", "help is available") and two new themes, and got uncoded down to 32%. The remaining uncoded comments are mostly generic ("help", "mental health"), and we report them openly instead of forcing them into a theme.
- **E3. Library API mismatch.** AI-written code used `width="stretch"` for Plotly charts, which this Streamlit version (1.50) doesn't support for `plotly_chart`. The resulting deprecation warnings were caught in automated app tests, and the code was reverted to the supported argument.
- **E4. Excel sheet name crash.** Generated sheet names included "/", which Excel doesn't allow, so the Export tab crashed. Caught by a headless app test (Streamlit AppTest) and fixed.
- **E5. Chart layout bugs the automated tests missed (found by a human reviewing the app).** The tests only checked that the app ran without errors, not how it looked. A team member found two problems by looking at the charts:
  - *Group gaps:* the value labels overlapped the confidence-interval whiskers. Fixed by placing each label past the end of its whisker (or past zero for negative values).
  - *Trends:* the response-count bars covered the outcome line. In Plotly, traces on the overlaying y-axis are drawn on top, and the AI had put the bars there. Fixed by swapping the axes so the line is drawn last, and making the bars partly transparent.
  - Lesson: visual output needs human review; "runs without errors" isn't enough.

## Manually verified numbers

`validate.py` recomputes 14 headline statistics directly from the raw Excel file with separate, simple pandas code: row count, % agree before/after and mean gain for all three items, NPS, county counts, and student count. All 14 match the pipeline exactly.

Example: "Can describe 988" goes from 46.5% agree before to 90.5% after (all 1,299 rows).
