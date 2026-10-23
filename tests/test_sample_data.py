import pandas as pd
from pathlib import Path

def test_sample_csv_has_required_fields_and_repeated_examples():
    path = Path(__file__).parents[1] / "data" / "sample_complaints.csv"
    df = pd.read_csv(path)
    assert "text" in df.columns
    assert len(df) >= 10
    assert df["demo_key"].is_unique
    assert df["text"].notna().all()
    assert df["location"].fillna("").ne("").any()
