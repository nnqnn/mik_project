import os
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "postgresql+asyncpg://payment:payment@localhost/payment"
os.environ["JWT_SECRET_KEY"] = "test-secret"

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture(autouse=True)
def dependency_overrides():
    async def fake_db():
        yield object()

    main.app.dependency_overrides[main.get_db] = fake_db
    main.app.dependency_overrides[main.get_current_user] = lambda: {
        "user_id": 1,
        "email": "user@example.com",
        "first_name": "Ivan",
        "last_name": "Ivanov",
    }
    main.app.dependency_overrides[main.get_rmq] = lambda: object()
    yield
    main.app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(main.app)


def payment(status="pending", customer_email="user@example.com"):
    return SimpleNamespace(
        payment_id="pay_test",
        status=status,
        order_id=42,
        amount=Decimal("1500.00"),
        currency="RUB",
        paid_at=datetime(2026, 1, 1, 12, 0, 0) if status == "paid" else None,
        signature="signature" if status == "paid" else None,
        customer_email=customer_email,
        created_at=datetime(2026, 1, 1, 11, 0, 0),
    )


def payment_payload():
    return {
        "order_id": 42,
        "amount": "1500.00",
        "currency": "RUB",
        "description": "Tickets",
        "success_url": "http://localhost/success",
        "fail_url": "http://localhost/fail",
        "webhook_url": "http://localhost/webhook",
    }


def test_health_and_metrics(client):
    assert client.get("/health").status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "mik_http_requests_total" in response.text
    assert "mik_http_request_duration_seconds" in response.text
    assert "mik_domain_events_total" in response.text


def test_create_payment(client, monkeypatch):
    async def fake_create_payment(db, payload, customer_email):
        assert customer_email == "user@example.com"
        return payment()

    monkeypatch.setattr(main, "create_payment", fake_create_payment)

    response = client.post("/payments", json=payment_payload())

    assert response.status_code == 201
    assert response.json()["payment_id"] == "pay_test"
    assert response.json()["payment_url"].endswith("/payments/pay_test")


def test_pay_payment_publishes_event(client, monkeypatch):
    published = []

    async def fake_get_payment(db, payment_id):
        return payment()

    async def fake_mark_paid(db, payment_id, signature):
        return payment(status="paid")

    async def fake_publish(rmq, routing_key, data):
        published.append((routing_key, data))

    monkeypatch.setattr(main, "get_payment_by_payment_id", fake_get_payment)
    monkeypatch.setattr(main, "mark_payment_paid", fake_mark_paid)
    monkeypatch.setattr(main, "publish_payment_event", fake_publish)

    response = client.post("/payments/pay_test/pay")

    assert response.status_code == 200
    assert response.json()["status"] == "paid"
    assert published[0][0] == "payment.completed"


def test_fail_payment_publishes_event(client, monkeypatch):
    published = []

    async def fake_get_payment(db, payment_id):
        return payment()

    async def fake_mark_failed(db, payment_id):
        return payment(status="failed")

    async def fake_publish(rmq, routing_key, data):
        published.append((routing_key, data))

    monkeypatch.setattr(main, "get_payment_by_payment_id", fake_get_payment)
    monkeypatch.setattr(main, "mark_payment_failed", fake_mark_failed)
    monkeypatch.setattr(main, "publish_payment_event", fake_publish)

    response = client.post("/payments/pay_test/fail")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert published[0][0] == "payment.failed"


def test_payment_owner_check(client, monkeypatch):
    async def fake_get_payment(db, payment_id):
        return payment(customer_email="other@example.com")

    monkeypatch.setattr(main, "get_payment_by_payment_id", fake_get_payment)

    response = client.get("/payments/pay_test")

    assert response.status_code == 403
