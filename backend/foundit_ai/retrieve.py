"""Step 1 of matching: cheap candidate retrieval. No model call.

Why: a model call costs seconds and tokens (free tier: 8K tokens/minute), Python
filtering costs microseconds. So we narrow the pool to a few plausible
candidates first and only send those to the model.

How:
1. Hard filters  - opposite type, still open, no clear category conflict.
2. Ranking       - TF-IDF cosine similarity over each report's public text plus
                   the attributes the model extracted at submit time (so
                   "navy school bag" and "dark blue backpack" share the words
                   "backpack" and "blue").

Private details are deliberately NOT used here; only the comparison step sees them.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from foundit_ai.schemas import ReportRecord

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "it", "its", "is", "was", "my", "i", "had", "has", "have", "there", "this",
    "that", "near", "left", "lost", "found", "someone", "some", "by", "from",
    "inside", "item", "very", "be", "been", "were", "am",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) > 1 and t not in _STOPWORDS]


def report_terms(r: ReportRecord) -> list[str]:
    """Words describing a report: public fields + model-extracted attributes."""
    parts = [r.description, r.category or "", r.color or "", r.location or ""]
    a = r.ai_attributes
    if a is not None and a.extraction_status == "ok":
        parts += [a.item_type or "", a.category or "", a.brand or "",
                  a.location_normalized or "", " ".join(a.color_family),
                  " ".join(a.features)]
    return _tokens(" ".join(parts))


def _category(r: ReportRecord) -> str | None:
    if r.category:
        return r.category
    a = r.ai_attributes
    return a.category if a is not None and a.extraction_status == "ok" else None


def categories_conflict(a: ReportRecord, b: ReportRecord) -> bool:
    ca, cb = _category(a), _category(b)
    return bool(ca and cb and ca != cb and "other" not in (ca, cb))


def tfidf_similarities(query_terms: list[str],
                       docs_terms: list[list[str]]) -> list[float]:
    """Cosine similarity between the query and each document.

    TF  = how often a word appears in this report.
    IDF = how rare the word is across all reports; rare words ("eiffel") count
          more than words every report shares ("bag").
    """
    all_docs = [query_terms] + docs_terms
    n = len(all_docs)
    df = Counter(term for doc in all_docs for term in set(doc))
    idf = {t: math.log((1 + n) / (1 + df[t])) + 1.0 for t in df}

    def vector(terms: list[str]) -> dict[str, float]:
        return {t: c * idf[t] for t, c in Counter(terms).items()}

    def norm(v: dict[str, float]) -> float:
        return math.sqrt(sum(x * x for x in v.values()))

    q = vector(query_terms)
    q_norm = norm(q)
    sims = []
    for terms in docs_terms:
        d = vector(terms)
        d_norm = norm(d)
        if q_norm == 0 or d_norm == 0:
            sims.append(0.0)
            continue
        dot = sum(w * d.get(t, 0.0) for t, w in q.items())
        sims.append(dot / (q_norm * d_norm))
    return sims


def search_candidate_reports(query: ReportRecord, pool: list[ReportRecord],
                             k: int = 5) -> tuple[list[ReportRecord], int]:
    """Return (top-k candidates, number of opposite-type open reports considered)."""
    if k <= 0:
        raise ValueError("k must be positive")

    opposite = [r for r in pool
                if r.type != query.type and r.status == "open" and r.id != query.id]
    considered = len(opposite)
    compatible = [r for r in opposite if not categories_conflict(query, r)]
    if not compatible:
        return [], considered

    sims = tfidf_similarities(report_terms(query), [report_terms(r) for r in compatible])
    same_category = [_category(query) is not None and _category(query) == _category(r)
                     for r in compatible]

    # Keep a report only if it shares some words OR is the same category.
    ranked = [(sim, r) for sim, same, r in zip(sims, same_category, compatible)
              if sim > 0 or same]
    ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [r for _, r in ranked[:k]], considered
