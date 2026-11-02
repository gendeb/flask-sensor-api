import pytest

from app import create_app
from app.config import TestConfig


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    return app.test_client()


def test_health(client):
    assert client.get("/health").get_json() == {"status": "ok"}


def test_devices(client):
    data = client.get("/api/v1/devices").get_json()["data"]
    assert len(data) == 5


def test_pagination(client):
    page = client.get("/api/v1/readings?limit=100&offset=0").get_json()
    assert len(page["data"]) == 100
    assert page["meta"]["total"] == 500
    assert page["meta"]["next_offset"] == 100
    last = client.get("/api/v1/readings?limit=100&offset=400").get_json()
    assert last["meta"]["next_offset"] is None


def test_limit_is_capped(client):
    page = client.get("/api/v1/readings?limit=999999").get_json()
    assert page["meta"]["limit"] == 1000


def test_filter_by_device(client):
    page = client.get("/api/v1/readings?device_id=1&limit=1000").get_json()
    assert page["meta"]["total"] == 100
    assert all(r["device_id"] == 1 for r in page["data"])


def test_bad_params(client):
    assert client.get("/api/v1/readings?limit=0").status_code == 400


def test_not_found(client):
    assert client.get("/api/v1/readings/999999").status_code == 404


def test_create_reading(client):
    resp = client.post("/api/v1/readings", json={"device_id": 1, "temperature": 21.5, "humidity": 40})
    assert resp.status_code == 201
    assert client.get(f"/api/v1/readings/{resp.get_json()['id']}").status_code == 200


def test_create_reading_validation(client):
    assert client.post("/api/v1/readings", json={"device_id": 1}).status_code == 400
    assert client.post("/api/v1/readings", json={"device_id": 99, "temperature": 1, "humidity": 1}).status_code == 404
    assert client.post("/api/v1/readings", json={"device_id": 1, "temperature": 1, "humidity": 500}).status_code == 400


def test_stats(client):
    stats = client.get("/api/v1/stats/summary").get_json()
    assert stats["count"] == 500


def test_units_are_returned(client):
    expected = {"temperature": "C", "humidity": "%"}
    assert client.get("/api/v1/readings?limit=1").get_json()["meta"]["units"] == expected
    assert client.get("/api/v1/readings/1").get_json()["units"] == expected
    assert client.get("/api/v1/stats/summary").get_json()["units"] == expected
    assert client.get("/").get_json()["units"] == expected
