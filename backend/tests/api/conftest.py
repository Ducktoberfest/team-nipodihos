import pytest
from fastapi.testclient import TestClient

from app import ai_bridge
from app.main import app

from api_payloads import FOUND_BAG, LOST_BACKPACK


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Fresh DB + upload dir per test, and the mock matcher regardless of foundit_ai."""
    monkeypatch.setenv("FOUNDIT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("FOUNDIT_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(ai_bridge, "AI_MODULE_AVAILABLE", False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(client):
    """Reports 1 (lost) and 2-4 (found), so mock_matches.json candidates 2, 3, 4 exist."""
    ids = [client.post("/reports", json=LOST_BACKPACK).json()["id"]]
    for _ in range(3):
        ids.append(client.post("/reports", json=FOUND_BAG).json()["id"])
    assert ids == [1, 2, 3, 4]
    return client
