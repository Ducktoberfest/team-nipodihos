def test_matches_before_any_run(seeded):
    body = seeded.get("/reports/1/matches").json()
    assert body["report_id"] == 1
    assert body["generated_at"] is None
    assert body["candidates"] == []


def test_matches_unknown_report_is_404(client):
    assert client.post("/reports/42/matches").status_code == 404
    assert client.get("/reports/42/matches").status_code == 404


def test_run_matches_creates_match_rows(seeded):
    res = seeded.post("/reports/1/matches", json={"limit": 5})
    assert res.status_code == 200
    body = res.json()
    assert body["report_id"] == 1
    assert body["generated_at"] is not None
    assert [c["candidate_report_id"] for c in body["candidates"]] == [2, 4, 3]
    assert [c["match_id"] for c in body["candidates"]] == [1, 2, 3]
    for cand in body["candidates"]:
        assert cand["feedback_status"] == "pending"
        assert len(cand["score_breakdown"]) == 5
        # Candidate view comes from our DB, never with private fields
        assert "contact" not in cand["candidate"]
        assert "private_details" not in cand["candidate"]
        assert cand["candidate"]["description"].startswith("A navy school bag")
    assert "finder@example.edu" not in res.text

    assert seeded.get("/reports/1/matches").json() == body


def test_run_matches_without_body_and_limit(seeded):
    assert len(seeded.post("/reports/1/matches").json()["candidates"]) == 3
    assert len(seeded.post("/reports/1/matches", json={"limit": 1}).json()["candidates"]) == 1
    assert seeded.post("/reports/1/matches", json={"limit": 11}).status_code == 422


def test_feedback_confirmed_sets_both_reports_matched(seeded):
    match_id = seeded.post("/reports/1/matches").json()["candidates"][0]["match_id"]
    res = seeded.post(f"/matches/{match_id}/feedback",
                      json={"status": "confirmed", "note": "Keychain matched."})
    assert res.status_code == 200
    body = res.json()
    assert body["match_id"] == match_id
    assert body["feedback_status"] == "confirmed"
    assert body["updated_at"].endswith("Z")

    assert seeded.get("/reports/1").json()["status"] == "matched"
    assert seeded.get("/reports/2").json()["status"] == "matched"
    assert seeded.get("/reports/3").json()["status"] == "open"


def test_rerun_keeps_feedback(seeded):
    match_id = seeded.post("/reports/1/matches").json()["candidates"][0]["match_id"]
    seeded.post(f"/matches/{match_id}/feedback", json={"status": "confirmed"})
    rerun = seeded.post("/reports/1/matches").json()["candidates"][0]
    assert rerun["match_id"] == match_id
    assert rerun["feedback_status"] == "confirmed"


def test_feedback_validation_and_404(seeded):
    seeded.post("/reports/1/matches")
    bad = seeded.post("/matches/1/feedback", json={"status": "maybe"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"
    missing = seeded.post("/matches/999/feedback", json={"status": "rejected"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
