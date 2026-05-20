import os
import tempfile
from decimal import Decimal

os.environ["DATABASE_URL"] = (
    f"sqlite+aiosqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"
)
os.environ["JWT_SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app import models
from app.database import Base, SessionLocal, sync_engine
from app import main


@pytest.fixture(autouse=True)
def reset_database(monkeypatch):
    Base.metadata.create_all(bind=sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(delete(models.Booking))

    main.app.dependency_overrides[main.get_current_user] = lambda: {
        "user_id": 1,
        "email": "user@example.com",
        "first_name": "Ivan",
        "last_name": "Ivanov",
        "access_token": "token",
    }

    async def fake_publish(event_type, payload):
        return True

    monkeypatch.setattr(main.broker, "publish", fake_publish)
    yield
    main.app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


async def fake_match_info(match_id: int, seats=10):
    return {
        "match_id": match_id,
        "seats_available": seats,
        "unit_price": Decimal("1500.00"),
        "currency": "RUB",
        "status": "scheduled",
    }


def test_availability_endpoint(client, monkeypatch):
    async def fetch_match(match_id):
        return await fake_match_info(match_id, seats=5)

    monkeypatch.setattr(main, "fetch_match_ticketing_info", fetch_match)

    response = client.get("/matches/42/availability")

    assert response.status_code == 200
    assert response.json()["match_id"] == 42
    assert response.json()["available_seats"] == 5
    assert response.json()["can_reserve"] is True


def test_create_booking_success(client, monkeypatch):
    async def fetch_match(match_id):
        return await fake_match_info(match_id, seats=5)

    async def create_payment(booking, access_token):
        return {
            "payment_id": "pay_test",
            "payment_url": "http://localhost:8002/payments/pay_test",
            "status": "pending",
        }

    monkeypatch.setattr(main, "fetch_match_ticketing_info", fetch_match)
    monkeypatch.setattr(main, "create_payment_for_booking", create_payment)

    response = client.post("/bookings", json={"match_id": 42, "quantity": 2})

    assert response.status_code == 201
    assert response.json()["payment_id"] == "pay_test"
    assert response.json()["status"] == "pending_payment"
    assert response.json()["total_price"] == 3000.0


def test_create_booking_with_insufficient_seats(client, monkeypatch):
    async def fetch_match(match_id):
        return await fake_match_info(match_id, seats=1)

    monkeypatch.setattr(main, "fetch_match_ticketing_info", fetch_match)

    response = client.post("/bookings", json={"match_id": 42, "quantity": 2})

    assert response.status_code == 409
    assert response.json()["error"] == "Недостаточно доступных мест"


def test_metrics_endpoint(client):
    client.get("/matches/not-an-int/availability")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "mik_http_requests_total" in response.text
    assert "mik_http_request_duration_seconds" in response.text
    assert "mik_domain_events_total" in response.text
