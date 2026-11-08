"""Rule-based theme coding for the two open-ended survey questions.

Transparent and offline by design: every theme is a list of keyword / regex
patterns (English + Spanish) that staff can read and edit. A comment can carry
several themes. Accuracy was checked by hand-coding a random sample (see
`validate.py` / AI_LOG.md).
"""
from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd

# Theme -> regex patterns (case-insensitive, matched anywhere in the comment).
VALUABLE_THEMES: Dict[str, List[str]] = {
    "988 is for more than suicide / any concern": [
        r"not (just|only)", r"more than (just )?suicide", r"other than", r"any (problem|thing|reason|issue)",
        r"anything", r"no solo", r"don.?t have to be in (a )?crisis", r"not .*crisis", r"isn.?t (just|only)",
        r"don.?t (need|have) to (be|want)", r"overwhelm", r"stress", r"any (mental health|kind|crisis|type)",
    ],
    "Anyone can call, including for someone else": [
        r"\banyone\b", r"\beveryone\b", r"any age", r"for (a |your )?(friend|family|others|someone)",
        r"someone else", r"about a friend", r"cualquier", r"todos", r"minors", r"any ?one\b", r"\bteens?\b", r"\bkids\b",
    ],
    "When / how to use 988": [
        r"when to (use|call|reach)", r"how to (use|call|reach|contact)", r"when and how", r"how and when",
        r"when (you|i|we|one) (can|should)", r"cuando", r"c[oó]mo usar", r"when it.?s appropriate",
        r"reasons? (to|why|people) call", r"^(to )?call 988", r"call 988 (if|when)", r"when (you )?need", r"use (these|it|them) when",
    ],
    "Difference between 988 and 911": [r"\b911\b"],
    "Access: 24/7, free, confidential, text/chat, languages": [
        r"24/?7", r"any ?time", r"whenever", r"always (available|there|open)", r"\bfree\b", r"confidential",
        r"anonymous", r"\btext", r"\bchat", r"language", r"spanish", r"espa[nñ]ol", r"idioma", r"availab", r"accessib",
        r"privacy", r"all the time", r"always talk",
    ],
    "How 988 works (what happens on a call)": [
        r"how (it|988|they|the calls?|calls) (work|go|actually)", r"how .*works", r"process", r"who answers",
        r"responder", r"counselor", r"call ?back", r"what happens", r"routed", r"call center", r"how the call",
        r"example of the call", r"consent",
    ],
    "Recognizing warning signs": [
        r"\bsigns?\b", r"identify", r"recogni[sz]e", r"warning", r"symptom", r"se[nñ]al", r"risk factor",
        r"protective factor",
    ],
    # Numbers other than 988/911 themselves (an earlier version matched "988" here and over-counted).
    "Statistics and facts": [
        r"\b(?!988\b|911\b|365\b)\d{3,}\b", r"\d{1,3},\d{3}", r"\d+\s?(%|k\b)", r"statistic", r"percent", r"every \d+ (minutes|seconds)", r"#1",
        r"\brates?\b", r"died", r"\d+ (minutes|seconds|people|students)",
    ],
    "Help is available / someone will listen": [
        r"(there is|there.?s) (always )?help", r"help is (always )?available", r"here to help", r"they (will|can) help",
        r"listen", r"judge", r"support", r"escuch", r"contar con", r"ayuda", r"someone (to talk|who understands)",
    ],
    "How to support someone in crisis": [
        r"help (a |your |my )?(friend|family|others|someone|people)", r"talk to (an individual|someone in|a friend)",
        r"de-?escalat", r"how to ask", r"what you can (to )?do", r"advocate", r"recommend 988", r"share 988",
        r"tell (friends|someone)", r"refer",
    ],
    "Other resources (warmline, services)": [r"warm ?line", r"resource", r"services", r"mobile crisis"],
    "Reducing stigma / it's OK to ask for help": [
        r"(it.?s )?ok(ay)? to", r"stigma", r"died by", r"committed", r"ask(ing)? for help", r"not alone",
        r"reach out", r"talk to someone", r"express", r"no (one|body) needs to wait",
    ],
    "General: what 988 is / everything": [
        r"what 988 is", r"^(the )?(988|number|phone number|hotline)\W*$", r"^(every ?thing|all( of it)?|todo)\b",
        r"learn(ing|ed)? (more )?about (988|it)", r"^(the )?988 (hotline|number|thing)", r"^el 988",
    ],
}

IMPROVE_THEMES: Dict[str, List[str]] = {
    "More interactive / engaging": [
        r"interact", r"activit", r"game", r"kahoot", r"engag", r"involv", r"hands.?on", r"discussion",
        r"ask (people|the audience|questions)", r"participat", r"din[aá]mic",
    ],
    "More videos, visuals, real examples": [
        r"video", r"visual", r"picture", r"stor(y|ies)", r"testimon", r"bring(ing)? someone", r"image", r"example", r"demonstrat", r"real (life|call|story)",
        r"scenario", r"role.?play", r"show (us|how|a)",
    ],
    "Longer / more depth": [
        r"longer", r"more time", r"more (info|information|detail|depth|lessons|about)", r"in.?depth",
        r"extend", r"m[aá]s informaci[oó]n",
    ],
    "Pacing and delivery": [
        r"slow", r"speed", r"too fast", r"faster", r"shorter", r"too long", r"boring", r"repetit",
        r"louder", r"speak (up|clear)", r"monoton", r"pace",
    ],
    "Logistics, tech, food, scheduling": [
        r"tech", r"audio", r"sound", r"\bmic", r"couldn.?t (see|hear)", r"room", r"food", r"snack", r"juice",
        r"pizza", r"registration", r"schedul", r"time of", r"seat",
        r"in.?person", r"print", r"screen", r"flyer", r"email",
    ],
    "Spanish / language access": [r"spanish", r"espa[nñ]ol", r"language", r"translat", r"interpret", r"idioma"],
    "Reach more people (schools, parents, ads)": [
        r"more (people|students|schools|parents)", r"advertis", r"social media", r"\bnews\b", r"broadcast",
        r"spread (the )?(word|awareness)", r"every school", r"adding students", r"que todas las personas",
        r"assembl", r"young people", r"temprana edad", r"everyone hears", r"informando",
    ],
    "Q: confidentiality / police involvement": [
        r"police", r"\bcops?\b", r"confidential", r"secre", r"anonymous", r"track", r"location",
        r"where you live", r"report", r"(parents?|mom|dad) (find|know)", r"tell (my|your) parents", r"privacy",
    ],
    "Q: how 988 works / who answers": [
        r"who answers", r"\btext", r"\bchat", r"how (does|do) (it|988|they)", r"call cent", r"counselor",
        r"responder", r"how are they open", r"request to talk", r"refuse", r"what happens",
    ],
    "Q: statistics, history, effectiveness": [
        r"how many", r"how often", r"statistic", r"when was", r"how did 988 start", r"effective", r"per (day|year)",
        r"a (day|year)\b", r"percent",
    ],
    "Q: where 988 is available": [
        r"countr", r"world ?wide", r"canada", r"mexico", r"every state", r"nationwide", r"territor", r"other states",
    ],
    "Q: when it's OK to call": [
        r"when to (use|call)", r"can (i|you|we) call (when|if|for|about)", r"if (you|i) can call", r"by accident",
        r"get in trouble", r"reasons to call", r"when should",
    ],
    "Q: careers / getting involved": [r"\bjob\b", r"career", r"become a", r"volunteer", r"work (at|for) 988"],
}

NO_CHANGE_PATTERNS = [
    r"^(n/?a|na|no|none|nope|nothing|nada|ninguna|idk|i don.?t know|no comment|no thanks?|no thank you)\b",
    r"no (further )?(questions|suggestions|improvements?)", r"i (have|got) no questions", r"don.?t have (any )?questions",
    r"nothing (to improve|else|more)", r"(it was|it.?s|everything was|was) (great|good|perfect|amazing|awesome|fine|excellent|exceptional)",
    r"(no|not) (need|needed) (for|to)", r"(fine|good|perfect) as is", r"no improvement", r"keep (it|doing)",
    r"todo (fue|est[aá]) bien", r"no (hay|tengo)", r"^(great|good|amazing|awesome|excellent) (training|presentation|job)",
    r"already (good|great|amazing|perfect)", r"me gust", r"genial", r"well put together", r"very informative",
    r"(was|is) (actually |really )?(perfect|great|good)", r"asi esta bien",
]

_PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[email]"),
    (re.compile(r"(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"), "[phone]"),
]

_compiled = {}


def _rx(pattern: str) -> re.Pattern:
    if pattern not in _compiled:
        _compiled[pattern] = re.compile(pattern, re.IGNORECASE)
    return _compiled[pattern]


def redact(text):
    """Remove emails and phone numbers before comments are displayed or exported."""
    if not isinstance(text, str):
        return text
    for rx, repl in _PII_PATTERNS:
        text = rx.sub(repl, text)
    return text


def is_question(text: str) -> bool:
    t = text.strip().lower()
    return "?" in t or bool(re.match(r"^(how|what|when|why|does|do|can|is|are|who|where|would|will|could|should|if)\b", t))


def code_comment(text, codebook: Dict[str, List[str]], no_change: bool = False) -> List[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    themes = [name for name, pats in codebook.items() if any(_rx(p).search(text) for p in pats)]
    if no_change and not themes and any(_rx(p).search(text) for p in NO_CHANGE_PATTERNS):
        return ["No changes needed / positive"]
    if not themes and no_change and is_question(text):
        return ["Q: other question about 988"]
    return themes or ["Uncoded / other"]


def code_comments(df: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per (response, question, theme)."""
    rows = []
    for _, r in df.iterrows():
        for col, book, nc, q in (
            ("comment_valuable", VALUABLE_THEMES, False, "Most valuable thing learned"),
            ("comment_improve", IMPROVE_THEMES, True, "How to improve / questions"),
        ):
            text = r.get(col)
            if not isinstance(text, str):
                continue
            for theme in code_comment(text, book, nc):
                rows.append({"response_id": r["response_id"], "Question": q, "Theme": theme,
                             "Comment": redact(text), "Is question": is_question(text),
                             "county": r["county"], "role_group": r["role_group"], "language": r["language"]})
    return pd.DataFrame(rows, columns=["response_id", "Question", "Theme", "Comment", "Is question",
                                       "county", "role_group", "language"])


def theme_counts(coded: pd.DataFrame, question: str, n_comments: int) -> pd.DataFrame:
    sub = coded[coded["Question"] == question]
    out = sub.groupby("Theme")["response_id"].nunique().rename("Comments").reset_index()
    out["% of comments"] = 100 * out["Comments"] / max(n_comments, 1)
    return out.sort_values("Comments", ascending=False).reset_index(drop=True)
