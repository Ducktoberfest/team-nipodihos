from api_payloads import FOUND_BAG

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


def test_upload_and_fetch_photo(client):
    client.post("/reports", json=FOUND_BAG)
    res = client.post("/reports/1/photo", files={"file": ("../../evil.png", PNG, "image/png")})
    assert res.status_code == 200
    assert res.json()["has_photo"] is True
    assert res.json()["photo_url"] == "/reports/1/photo"

    photo = client.get("/reports/1/photo")
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"
    assert photo.content == PNG


def test_wrong_type_is_415(client):
    client.post("/reports", json=FOUND_BAG)
    res = client.post("/reports/1/photo", files={"file": ("a.txt", b"hello", "text/plain")})
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "unsupported_media_type"
    # Claims to be PNG but isn't
    fake = client.post("/reports/1/photo", files={"file": ("a.png", b"not an image", "image/png")})
    assert fake.status_code == 415


def test_too_large_is_413(client):
    client.post("/reports", json=FOUND_BAG)
    big = PNG + b"\x00" * (5 * 1024 * 1024)
    res = client.post("/reports/1/photo", files={"file": ("a.png", big, "image/png")})
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "file_too_large"


def test_photo_404s(client):
    assert client.post("/reports/1/photo", files={"file": ("a.png", PNG, "image/png")}).status_code == 404
    client.post("/reports", json=FOUND_BAG)
    assert client.get("/reports/1/photo").status_code == 404
