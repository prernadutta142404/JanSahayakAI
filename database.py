"""SQLite persistence layer. The database path can be overridden with JANSAHAYAK_DB."""
from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
DEFAULT_DB = Path(__file__).parent / "jansahayak.db"
STATUSES = {"New", "Under Review", "Assigned", "In Progress", "Resolved"}
def utc_now() -> str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def connect(db_path=None):
    path = Path(db_path or os.getenv("JANSAHAYAK_DB", DEFAULT_DB))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
@contextmanager
def db_session(db_path=None):
    conn = connect(db_path)
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
def init_db(db_path=None):
    with db_session(db_path) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS complaints (
          id TEXT PRIMARY KEY, text TEXT NOT NULL CHECK(length(text) BETWEEN 1 AND 10000),
          platform TEXT NOT NULL DEFAULT 'Manual', post_url TEXT DEFAULT '', created_at TEXT NOT NULL,
          location TEXT DEFAULT '', latitude REAL, longitude REAL, likes INTEGER NOT NULL DEFAULT 0 CHECK(likes>=0),
          comments_count INTEGER NOT NULL DEFAULT 0 CHECK(comments_count>=0), shares INTEGER NOT NULL DEFAULT 0 CHECK(shares>=0),
          source_type TEXT NOT NULL DEFAULT 'user-supplied', source_filename TEXT DEFAULT '',
          category TEXT NOT NULL DEFAULT 'other', certainty TEXT DEFAULT 'low', confidence REAL DEFAULT 0,
          evidence TEXT DEFAULT '[]', explanation TEXT DEFAULT '', intent TEXT DEFAULT 'unknown',
          sentiment TEXT DEFAULT 'neutral', keywords TEXT DEFAULT '[]', needs_review INTEGER DEFAULT 1,
          priority_score INTEGER DEFAULT 0, priority TEXT DEFAULT 'low', priority_reasons TEXT DEFAULT '[]',
          department TEXT DEFAULT 'General Grievance Desk', department_reason TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'New', created_record_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS status_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id TEXT NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
          old_status TEXT, new_status TEXT NOT NULL, changed_at TEXT NOT NULL, note TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS duplicate_reviews (
          id INTEGER PRIMARY KEY AUTOINCREMENT, left_id TEXT NOT NULL, right_id TEXT NOT NULL,
          similarity REAL NOT NULL, decision TEXT NOT NULL DEFAULT 'pending',
          reviewer_note TEXT DEFAULT '', updated_at TEXT NOT NULL,
          UNIQUE(left_id, right_id)
        );
        """)
def add_complaint(record: dict, db_path=None) -> str:
    text = str(record.get("text", "")).strip()
    if not text or len(text) > 10000: raise ValueError("Complaint text must contain 1–10000 characters.")
    for key in ("likes", "comments_count", "shares"):
        value = record.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{key} must be a non-negative integer.")
    status = record.get("status", "New")
    if status not in STATUSES: raise ValueError("Invalid complaint status.")
    for key, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        value = record.get(key)
        if value is not None and value != "":
            try: numeric = float(value)
            except (ValueError, TypeError): raise ValueError(f"{key} must be a valid number.")
            if not low <= numeric <= high: raise ValueError(f"{key} must be between {low} and {high}.")
            record[key] = numeric
    confidence = float(record.get("confidence", 0))
    if not 0 <= confidence <= 1: raise ValueError("confidence must be between 0 and 1.")
    cid = str(record.get("id") or uuid.uuid4())
    now = utc_now()
    fields = ["id","text","platform","post_url","created_at","location","latitude","longitude","likes","comments_count","shares",
    "source_type","source_filename","category","certainty","confidence","evidence","explanation","intent","sentiment","keywords",
    "needs_review","priority_score","priority","priority_reasons","department","department_reason","status","created_record_at","updated_at"]
    values = [cid,text,record.get("platform","Manual"),record.get("post_url",""),record.get("created_at") or now,
    record.get("location",""),record.get("latitude"),record.get("longitude"),record.get("likes",0),record.get("comments_count",0),record.get("shares",0),
    record.get("source_type","user-supplied"),record.get("source_filename",""),record.get("category","other"),record.get("certainty","low"),
    float(record.get("confidence",0)),json.dumps(record.get("evidence",[]), ensure_ascii=False),record.get("explanation",""),
    record.get("intent","unknown"),record.get("sentiment","neutral"),json.dumps(record.get("keywords",[]), ensure_ascii=False),
    int(bool(record.get("needs_review",True))),int(record.get("priority_score",0)),record.get("priority","low"),
    json.dumps(record.get("priority_reasons",[]), ensure_ascii=False),record.get("department","General Grievance Desk"),
    record.get("department_reason",""),status,now,now]
    with db_session(db_path) as c:
        c.execute(f"INSERT INTO complaints ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", values)
        c.execute("INSERT INTO status_history(complaint_id,old_status,new_status,changed_at,note) VALUES(?,?,?,?,?)",
                  (cid,None,status,now,"Complaint created"))
    return cid
def list_complaints(db_path=None):
    with db_session(db_path) as c: return [dict(r) for r in c.execute("SELECT * FROM complaints ORDER BY created_at DESC")]
def get_complaint(cid, db_path=None):
    with db_session(db_path) as c:
        row = c.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None
def update_status(cid: str, status: str, note: str = "", db_path=None):
    if status not in STATUSES: raise ValueError("Invalid complaint status.")
    with db_session(db_path) as c:
        row = c.execute("SELECT status FROM complaints WHERE id=?", (cid,)).fetchone()
        if not row: raise ValueError("Complaint not found.")
        now = utc_now()
        c.execute("UPDATE complaints SET status=?,updated_at=? WHERE id=?", (status,now,cid))
        c.execute("INSERT INTO status_history(complaint_id,old_status,new_status,changed_at,note) VALUES(?,?,?,?,?)",
                  (cid,row["status"],status,now,note[:500]))
def get_status_history(cid, db_path=None):
    with db_session(db_path) as c: return [dict(r) for r in c.execute("SELECT * FROM status_history WHERE complaint_id=? ORDER BY id", (cid,))]
def save_duplicate_review(left_id, right_id, similarity, decision, note="", db_path=None):
    if decision not in {"confirmed", "rejected", "pending"}: raise ValueError("Invalid duplicate decision.")
    with db_session(db_path) as c:
        c.execute("""INSERT INTO duplicate_reviews(left_id,right_id,similarity,decision,reviewer_note,updated_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(left_id,right_id) DO UPDATE SET similarity=excluded.similarity,
        decision=excluded.decision,reviewer_note=excluded.reviewer_note,updated_at=excluded.updated_at""",
        (left_id,right_id,float(similarity),decision,note[:500],utc_now()))
def get_duplicate_reviews(db_path=None):
    with db_session(db_path) as c: return [dict(r) for r in c.execute("SELECT * FROM duplicate_reviews ORDER BY updated_at DESC")]
