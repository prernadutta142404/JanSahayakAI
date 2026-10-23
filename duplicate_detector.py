"""Potential duplicate detection with TF-IDF cosine similarity and optional location boost."""
from __future__ import annotations
import re
from difflib import SequenceMatcher
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # graceful fallback when optional ML dependencies are absent
    TfidfVectorizer = cosine_similarity = None

def compare_texts(text_a: str, text_b: str) -> float:
    a, b = (text_a or "").strip(), (text_b or "").strip()
    if not a or not b: return 0.0
    if TfidfVectorizer is not None:
        try:
            matrix = TfidfVectorizer(ngram_range=(1, 2), stop_words=None).fit_transform([a, b])
            return float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
        except ValueError:
            pass
    return SequenceMatcher(None, re.sub(r"\\W+", " ", a.lower()), re.sub(r"\\W+", " ", b.lower())).ratio()

def find_duplicates(records: list[dict], threshold: float = 0.42) -> list[dict]:
    """Return pair candidates; location agreement adds explainable context, never auto-merges."""
    results = []
    for i, left in enumerate(records):
        for right in records[i + 1:]:
            similarity = compare_texts(str(left.get("text", "")), str(right.get("text", "")))
            left_loc = (left.get("location") or "").strip().lower()
            right_loc = (right.get("location") or "").strip().lower()
            same_location = bool(left_loc and right_loc and left_loc == right_loc)
            adjusted = min(1.0, similarity + (0.08 if same_location else 0))
            if adjusted >= threshold:
                reasons = [f"Text similarity {similarity:.0%}"]
                if same_location: reasons.append("reported locations match")
                if not left_loc or not right_loc: reasons.append("location missing for at least one report")
                results.append({"left_id": left.get("id"), "right_id": right.get("id"),
                                "similarity": round(similarity, 3), "adjusted_similarity": round(adjusted, 3),
                                "same_location": same_location, "reason": "; ".join(reasons),
                                "decision": "pending"})
    return results
