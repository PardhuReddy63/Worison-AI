from app import app


def test_ping():
    client = app.test_client()
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}
