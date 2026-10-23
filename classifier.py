"""Explainable, offline grievance classification for English and basic Hinglish."""
from __future__ import annotations
import re
from collections import Counter

CATEGORIES = {
    "roads/potholes": ["pothole", "road", "street", "gaddha", "sadak", "broken road", "footpath", "bridge"],
    "water supply": ["water", "paani", "pipeline", "tap", "leakage", "no supply", "jal", "sewage water"],
    "electricity": ["electricity", "power cut", "bijli", "transformer", "street light", "blackout", "wire"],
    "sanitation": ["garbage", "kachra", "waste", "drain", "naali", "sewer", "dirty", "sanitation", "overflowing"],
    "public infrastructure": ["park", "bus stop", "public toilet", "bench", "building", "footpath", "school"],
    "civic safety": ["unsafe", "accident", "open manhole", "crime", "harassment", "danger", "fire", "exposed wire"],
}
INTENT_TERMS = ["please", "request", "complaint", "complain", "fix", "repair", "urgent", "resolve", "kindly",
                "kripya", "please solve", "samasya", "shikayat", "action", "help", "issue", "problem", "nahi aa", "not working"]
POSITIVE = {"good", "great", "thank", "resolved", "fixed", "working", "excellent", "thanks", "accha"}
NEGATIVE = {"bad", "terrible", "angry", "frustrated", "unsafe", "broken", "worst", "dirty", "urgent", "problem", "issue", "blocked", "leaking"}

def _terms(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z]+|[\u0900-\u097F]+", text.lower())

def classify_grievance(text: str) -> dict:
    """Return transparent rule-based category, intent, sentiment, evidence and review flag."""
    clean = (text or "").strip()
    if not clean:
        return {"category": "other", "certainty": "low", "confidence": 0.0, "evidence": [],
                "explanation": "No text supplied; human review required.", "intent": "unknown",
                "sentiment": "neutral", "keywords": [], "needs_review": True}
    lower = clean.lower()
    scores = {}
    evidence_by_category = {}
    for category, terms in CATEGORIES.items():
        found = [term for term in terms if term in lower]
        if found:
            scores[category] = len(found)
            evidence_by_category[category] = found
    if not scores:
        category, evidence, confidence, certainty = "other", [], 0.25, "low"
        explanation = "No category keywords matched; human review required."
        needs_review = True
    else:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        category, score = ordered[0]
        evidence = evidence_by_category[category]
        tie = len(ordered) > 1 and ordered[1][1] == score
        confidence = min(0.95, 0.55 + 0.12 * score) if not tie else 0.45
        certainty = "medium" if tie or score == 1 else "high"
        needs_review = tie or score == 1
        explanation = f"Matched {len(evidence)} keyword(s) for {category}: {', '.join(evidence)}."
        if tie:
            explanation += " Multiple categories matched equally; human review required."
    words = set(_terms(lower))
    intent = "complaint/request" if any(term in lower for term in INTENT_TERMS) or scores else "unclear"
    pos = sum(1 for w in words if w in POSITIVE)
    neg = sum(1 for w in words if w in NEGATIVE)
    sentiment = "negative" if neg > pos else "positive" if pos > neg else "neutral"
    keyword_counts = Counter(_terms(lower))
    keywords = [w for w, _ in keyword_counts.most_common(8) if len(w) > 2]
    return {"category": category, "certainty": certainty, "confidence": round(confidence, 2),
            "evidence": evidence, "explanation": explanation, "intent": intent,
            "sentiment": sentiment, "keywords": keywords, "needs_review": needs_review}
