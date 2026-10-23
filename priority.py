"""Explainable priority scoring; recommendation only, not an emergency determination."""
from datetime import datetime, timezone
SEVERITY = {
    "high": ["danger", "accident", "fire", "open manhole", "exposed wire", "hospital", "unsafe", "injury", "flood"],
    "medium": ["urgent", "overflow", "blocked", "no water", "power cut", "leaking", "pothole", "broken"],
}
def calculate_priority(text: str, created_at: str | None = None, volume: int = 1,
                       engagement: int = 0, now: datetime | None = None) -> dict:
    text = (text or "").lower()
    reasons, score = [], 0
    high = [x for x in SEVERITY["high"] if x in text]
    medium = [x for x in SEVERITY["medium"] if x in text]
    if high:
        score += 45
        reasons.append("High-severity indicator(s): " + ", ".join(high))
    elif medium:
        score += 25
        reasons.append("Moderate-severity indicator(s): " + ", ".join(medium))
    if volume >= 5:
        score += 25; reasons.append(f"Recurring volume is high ({volume} reports).")
    elif volume >= 2:
        score += 12; reasons.append(f"Related reports exist ({volume} reports).")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            ref = now or datetime.now(timezone.utc)
            if ref.tzinfo is None: ref = ref.replace(tzinfo=timezone.utc)
            days = max(0, (ref - dt).total_seconds() / 86400)
            if days >= 7: score += 20; reasons.append(f"Reported duration is at least 7 days ({int(days)} days).")
            elif days >= 2: score += 10; reasons.append(f"Reported duration is at least 2 days ({int(days)} days).")
        except (ValueError, TypeError):
            reasons.append("Timestamp could not be parsed; duration not scored.")
    # Engagement is deliberately capped and has low weight; it is not severity evidence.
    if engagement >= 100: score += 5; reasons.append("Engagement contributes only a small capped signal (+5).")
    elif engagement >= 20: score += 2; reasons.append("Engagement contributes only a small capped signal (+2).")
    score = min(100, score)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"
    if not reasons: reasons.append("No configured severity, recurrence, duration or engagement signals.")
    return {"score": score, "priority": level, "reasons": reasons,
            "disclaimer": "Suggested triage only; verify with a human. This score does not confirm an emergency."}
