from api_payloads import FOUND_BAG, LOST_BACKPACK

PRIVATE_FIELDS = ("contact", "private_details")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "ai_available": False}


def test_create_report_returns_public_view(client):
    res = client.post("/reports", json=LOST_BACKPACK)
    assert res.status_code == 201
    body = res.json()
    assert body["id"] == 1
    assert body["status"] == "open"
    assert body["has_private_details"] is True
    assert body["has_photo"] is False and body["photo_url"] is None
    assert body["ai_attributes"]["extraction_status"] == "pending"
    assert body["created_at"].endswith("Z")
    for field in PRIVATE_FIELDS:
        assert field not in body


def test_only_type_and_description_required(client):
    res = client.post("/reports", json={"type": "found", "description": "  Black umbrella found  "})
    assert res.status_code == 201
    assert res.json()["description"] == "Black umbrella found"
    assert res.json()["has_private_details"] is False


def test_short_description_uses_error_format(client):
    res = client.post("/reports", json={"type": "lost", "description": "  hi       "})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "validation_error"
    assert {"field": "description", "issue": "too_short"} in error["details"]


def test_future_occurred_at_rejected(client):
    res = client.post("/reports", json={**FOUND_BAG, "occurred_at": "2999-01-01T00:00:00Z"})
    assert res.status_code == 422
    assert "future" in res.json()["error"]["message"]


def test_invalid_category_rejected(client):
    res = client.post("/reports", json={**FOUND_BAG, "category": "spaceship"})
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "category"


def test_list_and_get_never_leak_private_fields(client):
    created = client.post("/reports", json=LOST_BACKPACK).json()
    client.post("/reports", json=FOUND_BAG)

    listing = client.get("/reports").json()
    assert listing["total"] == 2
    assert [r["id"] for r in listing["items"]] == [2, 1]  # newest first
    single = client.get(f"/reports/{created['id']}").json()

    for report in [*listing["items"], single]:
        for field in PRIVATE_FIELDS:
            assert field not in report
    raw = client.get("/reports").text + client.get("/reports/1").text
    assert "student@example.edu" not in raw
    assert "Eiffel" not in raw


def test_list_filters_and_limit(client):
    client.post("/reports", json=LOST_BACKPACK)
    client.post("/reports", json=FOUND_BAG)
    client.post("/reports", json=FOUND_BAG)
    found = client.get("/reports", params={"type": "found", "limit": 1}).json()
    assert found["total"] == 2
    assert len(found["items"]) == 1
    assert client.get("/reports", params={"limit": 500}).status_code == 422


def test_unknown_report_is_404(client):
    res = client.get("/reports/999")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"


def test_data_survives_restart(client):
    from fastapi.testclient import TestClient

    from app.main import app

    client.post("/reports", json=LOST_BACKPACK)
    with TestClient(app) as fresh:
        assert fresh.get("/reports/1").status_code == 200
