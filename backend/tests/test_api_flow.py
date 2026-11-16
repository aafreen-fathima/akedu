"""End-to-end through the HTTP API: hours -> upload -> review -> crunch -> plan -> re-plan -> export."""


def _upload_all(client, samples):
    ids = []
    for name in ["COMP6481_Outline_Sample.pdf", "COMP6231_Outline_Sample.pdf", "COMP6721_Outline_Sample.pdf"]:
        with open(samples[name], "rb") as f:
            r = client.post("/api/v1/documents", files={"file": (name, f, "application/pdf")})
        assert r.status_code == 202, r.text
        ids.append(r.json()["job"]["id"])
    return ids


def test_full_flow(client, user, samples):
    # R1 reserved hours: Mon, Tue, Thu co-op
    slots = [{"weekday": d, "start_time": "09:00", "end_time": "17:00", "label": "Co-op"} for d in (0, 1, 3)]
    r = client.put("/api/v1/reserved-hours", json=slots)
    assert r.status_code == 200 and len(r.json()) == 3

    # R2/R3 upload and extraction (TestClient runs the background job after the response)
    for job_id in _upload_all(client, samples):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] == "succeeded", job
        assert job["provider"] == "heuristic" and job["item_count"] >= 3

    docs = client.get("/api/v1/documents").json()
    assert {d["course_code"] for d in docs} == {"COMP 6481", "COMP 6231", "COMP 6721"}

    # R4: nothing is flagged before confirmation
    pending = client.get("/api/v1/assessments", params={"status": "extracted"}).json()
    assert len(pending) >= 10
    assert client.get("/api/v1/crunch").json() == []

    # a Week-N item resolves to a date and carries a review note
    week_item = next(a for a in pending if "presentations" in a["title"].lower())
    assert week_item["due_date"] == "2026-11-16" and "Week 10" in week_item["review_note"]

    # confirm everything that has a date
    ids = [a["id"] for a in pending if a["due_date"]]
    r = client.post("/api/v1/assessments/confirm", json={"ids": ids})
    assert r.status_code == 200

    # R6: Oct 20-23 crunch (midterm 25 + milestone 15 + assignment 10)
    crunch = client.get("/api/v1/crunch").json()
    oct_period = next(p for p in crunch if p["start"] == "2026-10-20")
    assert oct_period["end"] == "2026-10-23" and oct_period["count"] == 3 and oct_period["total_weight"] == 50

    # R7: editing a date recomputes flags on the next read
    milestone = next(a for a in client.get("/api/v1/assessments").json() if a["title"] == "Project milestone 2")
    r = client.patch(f"/api/v1/assessments/{milestone['id']}", json={"due_date": "2026-11-27"})
    assert r.status_code == 200
    crunch = client.get("/api/v1/crunch").json()
    assert all(milestone["id"] not in p["assessment_ids"] for p in crunch if p["start"] == "2026-10-20")
    client.patch(f"/api/v1/assessments/{milestone['id']}", json={"due_date": "2026-10-22"})

    # R8/R9 plan
    plan = client.post("/api/v1/plans").json()
    assert plan["version"] == 1 and plan["is_valid"], plan["validation_errors"]
    assert plan["full_weekdays"] == [0, 1, 3]
    assert plan["blocks"]

    # R10 re-plan after adding a Friday shift
    client.put("/api/v1/reserved-hours", json=slots + [{"weekday": 4, "start_time": "09:00", "end_time": "17:00", "label": "Co-op"}])
    plan2 = client.post("/api/v1/plans", params={"trigger": "reserved hours changed"}).json()
    assert plan2["version"] == 2
    d = client.get("/api/v1/plans/latest/diff").json()
    assert d["previous_version"] == 1 and d["moved"]

    # R11 export
    r = client.get("/api/v1/export.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert r.text.count("BEGIN:VEVENT") >= len(plan2["blocks"])


def test_pdf_deleted_after_extraction(client, user, samples):
    from app.config import settings
    _upload_all(client, samples)
    assert list(settings.upload_dir.glob("*.pdf")) == []


def test_other_users_cannot_see_my_data(client, user, samples):
    r = client.post("/api/v1/assessments", json={"course_code": "SOEN 6841", "title": "Mid-report",
                                                  "type": "project", "due_date": "2026-11-09", "weight_percent": 10})
    assert r.status_code == 201
    aid = r.json()["id"]
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"email": "intruder@test.ca", "password": "secret123"})
    assert client.get("/api/v1/assessments").json() == []
    assert client.patch(f"/api/v1/assessments/{aid}", json={"title": "x"}).status_code == 404
    assert client.delete(f"/api/v1/assessments/{aid}").status_code == 404


def test_requires_sign_in(client):
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/assessments").status_code == 401


def test_upload_errors_are_clear(client, user):
    r = client.post("/api/v1/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "not_pdf"


def test_overlapping_slots_rejected(client, user):
    r = client.put("/api/v1/reserved-hours", json=[
        {"weekday": 2, "start_time": "09:00", "end_time": "12:00", "label": "A"},
        {"weekday": 2, "start_time": "11:00", "end_time": "13:00", "label": "B"},
    ])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "overlap"


def test_cannot_confirm_without_date(client, user):
    from app.db import SessionLocal
    from app.models import Assessment
    r = client.post("/api/v1/assessments", json={"course_code": "X 1", "title": "T", "due_date": "2026-11-01"})
    aid = r.json()["id"]
    with SessionLocal() as db:
        a = db.get(Assessment, aid)
        a.due_date, a.status = None, "extracted"
        db.commit()
    r = client.post("/api/v1/assessments/confirm", json={"ids": [aid]})
    assert r.status_code == 422
