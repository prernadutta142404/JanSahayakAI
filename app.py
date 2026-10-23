"""JanSahayak AI — local civic grievance intelligence dashboard."""
from __future__ import annotations
import io, json, os
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import plotly.express as px
import networkx as nx
from classifier import classify_grievance
from priority import calculate_priority
from duplicate_detector import find_duplicates
from location_service import suggest_department, extract_location
from media_analyzer import analyze_image, extract_video_frames, IMAGE_EXTS, VIDEO_EXTS, validate_upload
import database as db
from analytics import overview_metrics, category_counts, daily_counts, department_workload

st.set_page_config(page_title="JanSahayak AI | Civic Intelligence", page_icon="🏛️", layout="wide")
st.markdown("""<style>
.stApp{background:#071426;color:#eef6ff}.block-container{padding-top:1.5rem;max-width:1500px}
[data-testid="stMetric"]{background:#10243b;border:1px solid #24415d;padding:16px;border-radius:12px}
[data-testid="stSidebar"]{background:#0b1b2e}.hero{background:linear-gradient(110deg,#102b47,#0b3d4b);padding:25px;border:1px solid #24556b;border-radius:16px;margin-bottom:18px}
.hero h1{color:#f3fbff;margin:0}.muted{color:#a9bed0}.pill{color:#54e0c0}
div.stButton>button{border-radius:9px;border:1px solid #2f6378}
</style>""", unsafe_allow_html=True)
DB_PATH = os.getenv("JANSAHAYAK_DB")
db.init_db(DB_PATH)

def analyze_record(row):
    text = str(row.get("text", "")).strip()
    if not text: raise ValueError("Complaint text is required.")
    cl = classify_grievance(text)
    loc = extract_location(text, str(row.get("location", "") or ""))
    priority = calculate_priority(text, str(row.get("created_at", "") or ""), 1,
                                  int(row.get("likes",0))+int(row.get("comments_count",0))+int(row.get("shares",0)))
    dept = suggest_department(cl["category"], text)
    return {**row, **cl, **loc, **priority, "priority_score": priority["score"],
            "priority": priority["priority"], "priority_reasons": priority["reasons"],
            "department": dept["department"], "department_reason": dept["reason"]}

def seed_demo():
    path = os.path.join(os.path.dirname(__file__), "data", "sample_complaints.csv")
    frame = pd.read_csv(path).fillna("")
    existing = db.list_complaints(DB_PATH)
    existing_demo = {r["source_filename"] for r in existing if r["source_type"] == "synthetic-demo"}
    inserted = 0
    for _, row in frame.iterrows():
        source_key = str(row.get("demo_key", ""))
        if source_key and source_key in existing_demo: continue
        record = analyze_record({"text": str(row["text"]), "platform": str(row.get("platform","Demo")),
            "post_url": str(row.get("post_url","")), "created_at": str(row.get("created_at","")),
            "location": str(row.get("location","")), "likes": int(row.get("likes",0)),
            "comments_count": int(row.get("comments_count",0)), "shares": int(row.get("shares",0)),
            "source_type":"synthetic-demo", "source_filename": source_key})
        record["status"] = str(row.get("status","New")) if str(row.get("status","New")) in db.STATUSES else "New"
        db.add_complaint(record, DB_PATH); inserted += 1
    return inserted

def load_data():
    return db.list_complaints(DB_PATH)

with st.sidebar:
    st.markdown("## 🏛️ JanSahayak AI")
    st.caption("Cyber Hackathon 2026 · PS-04")
    page = st.radio("Navigate", ["Overview", "Complaints", "Add / Import", "Media Lab", "Duplicate Review", "Analytics & Network", "About & Help"])
    st.divider()
    st.caption("Offline-first prototype · no live platform monitoring")
    if st.button("Load synthetic demo data", use_container_width=True):
        try: st.success(f"Added {seed_demo()} new synthetic records.")
        except Exception as exc: st.error(f"Could not load demo data: {exc}")

st.markdown('<div class="hero"><h1>JanSahayak AI</h1><p class="muted">Public Grievance Intelligence & Resolution Monitoring</p><span class="pill">● Evidence-led triage · Human-reviewed decisions</span></div>', unsafe_allow_html=True)
st.warning("Automated category, sentiment, location and priority suggestions can be wrong. Verify before taking action. Synthetic demo records are labelled; no live social-media connection is active.")
records = load_data()
duplicate_candidates = find_duplicates(records)
if page == "Overview":
    metrics = overview_metrics(records, duplicate_candidates)
    cols = st.columns(5)
    for col, label, key in zip(cols, ["Total complaints","Pending","High priority","Possible repeats","Resolved"],
                               ["total","pending","high_priority","recurring_clusters","resolved"]):
        col.metric(label, metrics[key])
    if not records:
        st.info("No complaints yet. Load synthetic demo data from the sidebar or add a complaint.")
    else:
        left, right = st.columns(2)
        cc = category_counts(records)
        with left:
            st.subheader("Complaints by category")
            st.plotly_chart(px.bar(cc, x="category", y="complaints", color="category", template="plotly_dark"), use_container_width=True)
        with right:
            st.subheader("Complaint volume over time")
            dc = daily_counts(records)
            st.plotly_chart(px.line(dc, x="date", y="complaints", markers=True, template="plotly_dark"), use_container_width=True)
        st.subheader("Latest reports")
        view = pd.DataFrame(records)[["id","created_at","category","priority","status","location","department","text"]].head(8)
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.caption("Priority is a configurable triage recommendation, not a verified emergency rating.")
elif page == "Complaints":
    st.subheader("Complaint register")
    if not records: st.info("No records found. Add a complaint or load demo data.")
    else:
        df = pd.DataFrame(records)
        search = st.text_input("Search text, location, ID or department")
        cats = sorted(df["category"].dropna().unique().tolist())
        selected_cats = st.multiselect("Category", cats, default=cats)
        statuses = sorted(df["status"].dropna().unique().tolist())
        selected_status = st.multiselect("Status", statuses, default=statuses)
        priorities = sorted(df["priority"].dropna().unique().tolist())
        selected_priorities = st.multiselect("Priority", priorities, default=priorities)
        filtered = df[df["category"].isin(selected_cats) & df["status"].isin(selected_status) & df["priority"].isin(selected_priorities)]
        if search:
            mask = filtered.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            filtered = filtered[mask]
        sort_by = st.selectbox("Sort by", ["created_at","priority_score","category","status"], index=0)
        filtered = filtered.sort_values(sort_by, ascending=(sort_by != "priority_score"), na_position="last")
        st.dataframe(filtered[["id","created_at","text","category","sentiment","priority","priority_score","location","department","status","source_type"]],
                     use_container_width=True, hide_index=True)
        st.download_button("Export filtered CSV", filtered.to_csv(index=False).encode("utf-8-sig"),
                           "jansahayak_filtered_complaints.csv", "text/csv")
        ids = filtered["id"].tolist()
        if ids:
            chosen = st.selectbox("Open complaint detail", ids, format_func=lambda x: f"{x[:8]} · {filtered.loc[filtered.id==x,'category'].iloc[0]}")
            item = db.get_complaint(chosen, DB_PATH)
            with st.expander("Complaint details & lifecycle", expanded=True):
                st.write("**Source text:**", item["text"])
                st.write("**Source:**", item["source_type"], "·", item["platform"], item["post_url"])
                st.write("**Analysis evidence:**", item["explanation"])
                st.write("**Priority reasons:**", json.loads(item["priority_reasons"] or "[]"))
                st.write("**Department rationale:**", item["department_reason"])
                st.write("**Location metadata:**", item["location"] or "Missing", "· coordinates:", item["latitude"], item["longitude"])
                history = db.get_status_history(chosen, DB_PATH)
                st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
                with st.form("status_update"):
                    new_status = st.selectbox("Update status", sorted(db.STATUSES), index=sorted(db.STATUSES).index(item["status"]))
                    note = st.text_input("Update note (optional)")
                    if st.form_submit_button("Save status"):
                        try: db.update_status(chosen,new_status,note,DB_PATH); st.success("Status updated."); st.rerun()
                        except Exception as exc: st.error(f"Could not update status: {exc}")
elif page == "Add / Import":
    st.subheader("Add a grievance")
    with st.form("add_complaint", clear_on_submit=True):
        text = st.text_area("Post / complaint text *", max_chars=10000, height=130)
        c1,c2,c3 = st.columns(3)
        platform = c1.selectbox("Source platform", ["Manual","Instagram","Facebook","X / Twitter","YouTube","WhatsApp (lawfully supplied)","Other"])
        url = c2.text_input("Post URL (optional)")
        created_at = c3.text_input("Post timestamp (ISO format, optional)", placeholder="2026-10-23T12:30:00+05:30")
        location = st.text_input("Reported location (optional; do not guess)")
        a,b,c = st.columns(3)
        likes = a.number_input("Likes", min_value=0, max_value=10000000, value=0)
        comments = b.number_input("Comments", min_value=0, max_value=10000000, value=0)
        shares = c.number_input("Shares", min_value=0, max_value=10000000, value=0)
        submitted = st.form_submit_button("Analyse and save complaint", type="primary")
        if submitted:
            if not text.strip(): st.error("Enter complaint text before saving.")
            else:
                try:
                    if created_at.strip(): datetime.fromisoformat(created_at.strip().replace("Z","+00:00"))
                    result = analyze_record({"text":text.strip(),"platform":platform,"post_url":url.strip(),
                        "created_at":created_at.strip() or datetime.now(timezone.utc).isoformat(),
                        "location":location.strip(),"likes":int(likes),"comments_count":int(comments),"shares":int(shares),
                        "source_type":"user-supplied"})
                    cid = db.add_complaint(result, DB_PATH)
                    st.success(f"Saved complaint {cid}.")
                    st.json({k:result[k] for k in ["category","certainty","confidence","evidence","explanation","sentiment","priority","priority_reasons","department","department_reason","location","source"]})
                except ValueError as exc: st.error(f"Please check your input: {exc}")
                except Exception as exc: st.error(f"Could not save complaint. Check the fields and try again. ({type(exc).__name__})")
    st.divider()
    st.subheader("Import CSV")
    st.caption("Required column: text. Optional: platform, post_url, created_at, location, likes, comments_count, shares, status.")
    upload = st.file_uploader("Choose CSV", type=["csv"], key="csv_upload")
    if upload:
        try:
            if upload.size > 5*1024*1024: raise ValueError("CSV exceeds the 5 MB limit.")
            frame = pd.read_csv(upload)
            if "text" not in frame.columns: raise ValueError("CSV must include a 'text' column.")
            if len(frame)>2000: raise ValueError("CSV is limited to 2,000 rows per import.")
            st.write(f"Preview: {len(frame)} rows"); st.dataframe(frame.head(10),use_container_width=True)
            if st.button("Validate and import CSV"):
                successes, errors = 0, []
                for index,row in frame.iterrows():
                    try:
                        if pd.isna(row.get("text")) or not str(row.get("text","")).strip(): raise ValueError("empty text")
                        def safe_int(key):
                            val = row.get(key,0)
                            if pd.isna(val) or val=="": return 0
                            num = int(val)
                            if num < 0: raise ValueError(f"{key} cannot be negative")
                            return num
                        ts = row.get("created_at","")
                        ts = "" if pd.isna(ts) else str(ts).strip()
                        if ts: datetime.fromisoformat(ts.replace("Z","+00:00"))
                        rec = analyze_record({"text":str(row["text"]).strip(),"platform":str(row.get("platform","CSV")),
                            "post_url":str(row.get("post_url","")),"created_at":ts or datetime.now(timezone.utc).isoformat(),
                            "location":"" if pd.isna(row.get("location","")) else str(row.get("location","")),
                            "likes":safe_int("likes"),"comments_count":safe_int("comments_count"),"shares":safe_int("shares"),
                            "source_type":"csv-import"})
                        db.add_complaint(rec,DB_PATH); successes += 1
                    except Exception as exc: errors.append(f"Row {index+2}: {str(exc)[:160]}")
                st.success(f"Imported {successes} row(s).")
                if errors: st.error(f"{len(errors)} row(s) skipped."); st.write(errors[:20])
                st.rerun()
        except Exception as exc:
            st.error(f"Could not read this CSV. Check that it is a valid UTF-8 CSV file. ({type(exc).__name__})")
elif page == "Media Lab":
    st.subheader("Media text extraction")
    st.info("OCR extracts text only. Video frames are previews for human review; the app does not detect potholes, damage, faces, or locations from pixels.")
    media = st.file_uploader("Upload an image or video (max 25 MB)", type=sorted(IMAGE_EXTS|VIDEO_EXTS), key="media_upload")
    if media:
        data = media.getvalue()
        ok,msg = validate_upload(media.name,len(data))
        if not ok: st.error(msg)
        elif media.size > 25*1024*1024: st.error(msg)
        elif media.name.lower().endswith(tuple(IMAGE_EXTS)):
            result = analyze_image(data,media.name)
            st.write("**Filename:**",result["filename"],"· **Status:**",result["status"])
            st.caption(result["message"])
            st.text_area("Extracted text (verify manually)",result["text"],height=180)
            if result["text"] and st.button("Create complaint from OCR text"):
                rec = analyze_record({"text":result["text"],"platform":"Media upload","source_type":"media-ocr",
                                      "source_filename":result["filename"],"created_at":datetime.now(timezone.utc).isoformat()})
                cid=db.add_complaint(rec,DB_PATH); st.success(f"Created complaint {cid}")
        else:
            result=extract_video_frames(data,media.name)
            st.write("**Filename:**",result["filename"],"· **Status:**",result["status"]); st.caption(result["message"])
            for frame in result["frames"]:
                st.image(frame["jpeg_bytes"],caption=f"Frame index {frame['frame_index']}",use_container_width=True)
                if st.button(f"Run OCR on frame {frame['frame_index']}",key=f"ocr_{frame['frame_index']}"):
                    ocr=analyze_image(frame["jpeg_bytes"],f"{media.name}_frame_{frame['frame_index']}.jpg")
                    st.text_area("Extracted frame text",ocr["text"],key=f"text_{frame['frame_index']}")
elif page == "Duplicate Review":
    st.subheader("Potential duplicate complaints")
    st.caption("Text similarity creates a review candidate only. No records are automatically merged.")
    if not records: st.info("Add complaints or load demo data first.")
    else:
        candidates=find_duplicates(records)
        reviews={(r["left_id"],r["right_id"]):r for r in db.get_duplicate_reviews(DB_PATH)}
        if not candidates: st.success("No potential duplicates above the configured threshold.")
        for i,candidate in enumerate(candidates):
            left=db.get_complaint(candidate["left_id"],DB_PATH); right=db.get_complaint(candidate["right_id"],DB_PATH)
            saved=reviews.get((candidate["left_id"],candidate["right_id"]),{})
            with st.expander(f"{candidate['similarity']:.0%} text similarity · {candidate['reason']} · review: {saved.get('decision','pending')}"):
                a,b=st.columns(2)
                a.write(f"**{left['id'][:8]}** · {left['location'] or 'Location missing'}"); a.write(left["text"])
                b.write(f"**{right['id'][:8]}** · {right['location'] or 'Location missing'}"); b.write(right["text"])
                decision=st.radio("Review decision",["pending","confirmed","rejected"],index=["pending","confirmed","rejected"].index(saved.get("decision","pending")),horizontal=True,key=f"decision_{i}")
                note=st.text_input("Reviewer note",value=saved.get("reviewer_note",""),key=f"note_{i}")
                if st.button("Save review",key=f"save_{i}"):
                    db.save_duplicate_review(candidate["left_id"],candidate["right_id"],candidate["similarity"],decision,note,DB_PATH)
                    st.success("Review saved."); st.rerun()
elif page == "Analytics & Network":
    st.subheader("Trends, workload & relationship network")
    if not records: st.info("Load demo data or add complaints to explore analytics.")
    else:
        df=pd.DataFrame(records)
        left,right=st.columns(2)
        with left:
            st.plotly_chart(px.pie(df,names="priority",title="Suggested priority mix",template="plotly_dark"),use_container_width=True)
        with right:
            workload=department_workload(records)
            st.plotly_chart(px.bar(workload,x="department",y="complaints",color="status",title="Department workload by status",template="plotly_dark"),use_container_width=True)
        st.subheader("Related complaint graph")
        candidates=find_duplicates(records)
        graph=nx.Graph()
        for r in records: graph.add_node(r["id"][:8], label=(r["text"][:55]+"…") if len(r["text"])>55 else r["text"], category=r["category"])
        for edge in candidates: graph.add_edge(str(edge["left_id"])[:8],str(edge["right_id"])[:8],weight=edge["similarity"])
        if graph.number_of_edges():
            pos=nx.spring_layout(graph,seed=7)
            edges=list(graph.edges())
            edge_x=[]; edge_y=[]
            for u,v in edges: edge_x += [pos[u][0],pos[v][0],None]; edge_y += [pos[u][1],pos[v][1],None]
            import plotly.graph_objects as go
            fig=go.Figure()
            fig.add_trace(go.Scatter(x=edge_x,y=edge_y,mode="lines",line=dict(width=1,color="#4b7890"),hoverinfo="none"))
            fig.add_trace(go.Scatter(x=[pos[n][0] for n in graph.nodes()],y=[pos[n][1] for n in graph.nodes()],
                mode="markers+text",text=[n for n in graph.nodes()],textposition="top center",
                marker=dict(size=13,color="#25c7bc"),customdata=[graph.nodes[n]["label"] for n in graph.nodes()],
                hovertemplate="%{customdata}<extra></extra>"))
            fig.update_layout(template="plotly_dark",showlegend=False,margin=dict(l=10,r=10,t=10,b=10),xaxis_visible=False,yaxis_visible=False)
            st.plotly_chart(fig,use_container_width=True)
        else: st.info("No related complaint edges yet. Add repeated or similar reports to create a network.")
        coord_df=df.dropna(subset=["latitude","longitude"]) if {"latitude","longitude"}.issubset(df.columns) else pd.DataFrame()
        if not coord_df.empty:
            valid=coord_df[(coord_df.latitude.between(-90,90))&(coord_df.longitude.between(-180,180))]
            if not valid.empty: st.map(valid.rename(columns={"latitude":"lat","longitude":"lon"})[["lat","lon"]])
        else: st.info("Map unavailable: no validated latitude/longitude coordinates are stored. Locations are not geocoded or guessed.")
elif page == "About & Help":
    st.subheader("What is implemented")
    st.markdown("""
    - **Ingestion:** manual reports, CSV import with row-level validation, image OCR, selected video-frame extraction.
    - **Classification:** explainable bilingual keyword rules, evidence, certainty indicator, simple sentiment estimate and human-review flags.
    - **Triage:** configurable severity/recurrence/duration/engagement scoring with reasons.
    - **Duplicate review:** local TF-IDF cosine similarity, location context, human confirmation/rejection, no automatic merging.
    - **Operations:** SQLite persistence, status history, filtering, CSV export, Plotly charts and NetworkX relationship graph.
    - **Location:** accepts user-supplied locations and conservative explicit text patterns; no external geocoding.
    """)
    st.subheader("Important limitations")
    st.markdown("""
    - No social platform API or live monitoring is connected. Import only public or lawfully supplied data.
    - Classification, sentiment, keyword extraction and priority are deterministic heuristics, not trained AI models.
    - Hindi support is basic; OCR needs the Tesseract executable installed separately.
    - Video OCR runs on selected frames only. No image damage classification or automatic GPS extraction exists.
    - Map displays only supplied, valid coordinates; it does not infer coordinates from place names.
    - Prototype has no authentication, role-based access control or production deployment hardening. Use synthetic data for demos.
    """)
    st.subheader("Windows PowerShell quick start")
    st.code("py -3.12 -m venv .venv\n.\\.venv\\Scripts\\Activate.ps1\npython -m pip install --upgrade pip\npip install -r requirements.txt\nstreamlit run app.py",language="powershell")
    st.write("Tests: `python -m pytest -q`")
