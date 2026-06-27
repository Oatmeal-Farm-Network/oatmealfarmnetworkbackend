def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_loads(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    