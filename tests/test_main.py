from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_live():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_health_ready():
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    # Status can be "ready" or "degraded" depending on database availability
    assert data["status"] in ["ready", "degraded"]
    assert "database" in data


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Payment Service"
    assert "version" in data
    assert "endpoints" in data
