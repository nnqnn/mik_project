import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"
os.environ["JWT_SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient

from app import broker
from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    async def fake_publish(payload):
        return None

    monkeypatch.setattr(broker, "publish_user_registered_event", fake_publish)


@pytest.fixture
def client():
    return TestClient(app)


def user_payload(email="user@example.com"):
    return {
        "email": email,
        "password": "secret123",
        "first_name": "Ivan",
        "last_name": "Ivanov",
    }


def test_register_login_and_duplicate_email(client):
    register_response = client.post("/register", json=user_payload())
    assert register_response.status_code == 201
    assert register_response.json()["access_token"]

    duplicate_response = client.post("/register", json=user_payload())
    assert duplicate_response.status_code == 400

    login_response = client.post(
        "/login",
        json={"email": "user@example.com", "password": "secret123"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["token_type"] == "bearer"


def test_login_failure_and_metrics(client):
    response = client.post(
        "/login",
        json={"email": "missing@example.com", "password": "secret123"},
    )
    assert response.status_code == 401

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    assert "mik_http_requests_total" in metrics_response.text
    assert "mik_http_request_duration_seconds" in metrics_response.text
    assert "mik_domain_events_total" in metrics_response.text
