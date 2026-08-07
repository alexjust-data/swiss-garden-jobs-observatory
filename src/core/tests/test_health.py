from __future__ import annotations


def test_health_endpoint(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "swiss-garden-jobs-observatory"
