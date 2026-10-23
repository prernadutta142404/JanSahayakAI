"""Conservative location and department suggestions; no geocoding or coordinate invention."""
import re
DEPARTMENTS = {
    "roads/potholes": ("Roads & Public Works", ["road", "pothole", "sadak", "gaddha", "footpath"]),
    "water supply": ("Water Supply Department", ["water", "paani", "pipeline", "tap", "jal", "leakage"]),
    "electricity": ("Electricity Department", ["electricity", "power", "bijli", "transformer", "wire", "light"]),
    "sanitation": ("Sanitation & Drainage", ["garbage", "kachra", "drain", "naali", "sewer", "waste"]),
    "public infrastructure": ("Public Infrastructure", ["park", "bus stop", "toilet", "building", "footpath"]),
    "civic safety": ("Civic Safety / Municipal Control Room", ["unsafe", "accident", "manhole", "danger", "fire"]),
    "other": ("General Grievance Desk", []),
}
def suggest_department(category: str, text: str = "") -> dict:
    department, terms = DEPARTMENTS.get(category, DEPARTMENTS["other"])
    matched = [term for term in terms if term in (text or "").lower()]
    return {"department": department, "reason": f"Category '{category}' maps to {department}." +
            (f" Text evidence: {', '.join(matched)}." if matched else " No extra keyword evidence found."),
            "needs_review": category == "other"}
def extract_location(text: str, supplied_location: str | None = None) -> dict:
    supplied = (supplied_location or "").strip()
    if supplied:
        return {"location": supplied, "source": "user-supplied", "certainty": "provided", "needs_review": False}
    # Only extract explicit common locality markers; this is not a general-purpose NER model.
    patterns = [r"\b(?:at|near|in|outside|beside)\s+([A-Z][A-Za-z0-9 .'-]{2,45}?)(?=[,.!?]|$)",
                r"(?:स्थान|इलाका)\s*[:：]?\s*([\u0900-\u097F ]{2,30})"]
    for pattern in patterns:
        match = re.search(pattern, text or "")
        if match:
            value = match.group(1).strip()
            return {"location": value, "source": "text-extracted", "certainty": "low",
                    "needs_review": True}
    return {"location": "", "source": "missing", "certainty": "unknown", "needs_review": True}
