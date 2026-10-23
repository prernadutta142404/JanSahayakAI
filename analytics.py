"""Database-backed analysis helpers."""
import pandas as pd
def records_frame(records):
    df = pd.DataFrame(records)
    if not df.empty and "created_at" in df:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    return df
def overview_metrics(records, duplicate_candidates=None):
    records = list(records)
    return {"total": len(records), "pending": sum(r.get("status") != "Resolved" for r in records),
            "high_priority": sum(r.get("priority") == "high" for r in records),
            "resolved": sum(r.get("status") == "Resolved" for r in records),
            "recurring_clusters": len(duplicate_candidates or [])}
def category_counts(records):
    return records_frame(records).groupby("category").size().rename("complaints").reset_index() if records else pd.DataFrame(columns=["category","complaints"])
def daily_counts(records):
    df = records_frame(records)
    if df.empty: return pd.DataFrame(columns=["date","complaints"])
    df["date"] = df["created_at"].dt.date.astype(str)
    return df.groupby("date").size().rename("complaints").reset_index()
def department_workload(records):
    return records_frame(records).groupby(["department","status"]).size().rename("complaints").reset_index() if records else pd.DataFrame(columns=["department","status","complaints"])
