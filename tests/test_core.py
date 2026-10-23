import pytest
from classifier import classify_grievance
from priority import calculate_priority
from duplicate_detector import compare_texts, find_duplicates
from location_service import suggest_department, extract_location
from media_analyzer import validate_upload
import database as db

def test_classifier_detects_water_and_evidence():
    result = classify_grievance("Paani nahi aa raha, please restore water supply")
    assert result["category"] == "water supply"
    assert result["evidence"]
    assert result["intent"] == "complaint/request"

def test_unknown_requires_review():
    result = classify_grievance("Something happened yesterday")
    assert result["category"] == "other"
    assert result["needs_review"] is True

def test_priority_uses_severity_and_recurrence():
    result = calculate_priority("Exposed wire near school", volume=5, engagement=0)
    assert result["priority"] == "high"
    assert any("High-severity" in reason for reason in result["reasons"])

def test_engagement_is_capped_and_not_enough_for_high():
    result = calculate_priority("ordinary request", engagement=10000)
    assert result["score"] == 5
    assert result["priority"] == "low"

def test_duplicate_detection_and_location_context():
    assert compare_texts("pothole on main road", "pothole on main road") > 0.9
    candidates = find_duplicates([
        {"id":"a","text":"pothole on main road please repair","location":"Patna"},
        {"id":"b","text":"please repair pothole on main road","location":"Patna"}
    ], threshold=0.3)
    assert candidates and candidates[0]["same_location"]

def test_department_and_location_are_conservative():
    assert suggest_department("water supply","paani nahi aa raha")["department"] == "Water Supply Department"
    assert extract_location("Something happened")["location"] == ""
    assert extract_location("problem near Gandhi Maidan")["needs_review"] is True

@pytest.mark.parametrize("filename,size,expected", [
    ("photo.jpg", 100, True), ("video.mp4", 100, True), ("script.exe", 100, False),
    ("photo.png", 0, False), ("large.mp4", 26*1024*1024, False)
])
def test_upload_validation(filename,size,expected):
    assert validate_upload(filename,size)[0] is expected

def test_database_persistence_and_status_history(tmp_path):
    path = tmp_path / "test.sqlite"
    db.init_db(path)
    cid = db.add_complaint({"text":"Pothole needs repair","category":"roads/potholes"}, path)
    assert db.get_complaint(cid,path)["text"] == "Pothole needs repair"
    db.update_status(cid,"Under Review","triage",path)
    assert db.get_complaint(cid,path)["status"] == "Under Review"
    assert len(db.get_status_history(cid,path)) == 2

def test_database_rejects_empty_text(tmp_path):
    db.init_db(tmp_path/"test.sqlite")
    with pytest.raises(ValueError):
        db.add_complaint({"text":"  "},tmp_path/"test.sqlite")

def test_duplicate_review_persists(tmp_path):
    path=tmp_path/"test.sqlite"; db.init_db(path)
    db.save_duplicate_review("a","b",0.8,"confirmed","same locality",path)
    assert db.get_duplicate_reviews(path)[0]["decision"] == "confirmed"

def test_database_validates_coordinates_and_status(tmp_path):
    path=tmp_path/"test.sqlite"; db.init_db(path)
    with pytest.raises(ValueError):
        db.add_complaint({"text":"Report", "latitude":120},path)
    with pytest.raises(ValueError):
        db.add_complaint({"text":"Report", "status":"Closed"},path)
