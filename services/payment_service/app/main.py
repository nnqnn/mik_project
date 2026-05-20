import hashlib
import os
from contextlib import asynccontextmanager
from typing import Any

import aio_pika
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.broker.publisher import publish_payment_event
from app.config import settings
from app.crud import (
    create_payment,
    get_payment_by_payment_id,
    mark_payment_failed,
    mark_payment_paid,
)
from app.db import get_db
from app.metrics import metrics_middleware, metrics_response, record_domain_event
from app.schemas import (
    PaymentCreate,
    PaymentCreateResponse,
    PaymentStatusResponse,
)
from app.security import get_current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rmq_connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    yield
    await app.state.rmq_connection.close()


app = FastAPI(
    title="Payment Service",
    description="Payment microservice for football ticket booking",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        ",".join(
            [
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "http://localhost:8001",
                "http://127.0.0.1:8001",
                "http://localhost:8002",
                "http://127.0.0.1:8002",
                "http://localhost:8003",
                "http://127.0.0.1:8003",
            ]
        ),
    ).split(",")
    if origin.strip()
]
cors_origin_regex = os.getenv(
    "CORS_ORIGIN_REGEX",
    r"https?://(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(metrics_middleware)


def get_rmq(request: Request) -> aio_pika.RobustConnection:
    return request.app.state.rmq_connection


def payment_url(payment_id: str) -> str:
    return f"{settings.PAYMENT_PUBLIC_BASE_URL.rstrip('/')}/payments/{payment_id}"


def ensure_payment_owner(customer_email: str, current_user: dict[str, Any]) -> None:
    token_email = str(current_user["email"]).lower()
    if str(customer_email).lower() != token_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payment belongs to another user",
        )


def payment_status_payload(payment) -> dict[str, Any]:
    return {
        "payment_id": payment.payment_id,
        "status": payment.status,
        "order_id": payment.order_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "paid_at": payment.paid_at,
        "signature": payment.signature,
    }


@app.get("/health")
async def healthcheck():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.post("/payments", response_model=PaymentCreateResponse, status_code=201)
async def create_payment_endpoint(
    payload: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    payment = await create_payment(db, payload, str(current_user["email"]))
    record_domain_event("payment_created")
    return {
        "payment_id": payment.payment_id,
        "status": payment.status,
        "order_id": payment.order_id,
        "amount": payment.amount,
        "currency": payment.currency,
        "payment_url": payment_url(payment.payment_id),
        "created_at": payment.created_at,
    }


@app.get("/payments/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_endpoint(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    payment = await get_payment_by_payment_id(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    ensure_payment_owner(payment.customer_email, current_user)
    return payment_status_payload(payment)


@app.post("/payments/{payment_id}/pay", response_model=PaymentStatusResponse)
async def pay_payment_endpoint(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    rmq: aio_pika.RobustConnection = Depends(get_rmq),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    payment = await get_payment_by_payment_id(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    ensure_payment_owner(payment.customer_email, current_user)

    if payment.status == "paid":
        return payment_status_payload(payment)
    if payment.status == "failed":
        raise HTTPException(status_code=400, detail="Payment already failed")

    signature = hashlib.sha256(
        f"{payment.payment_id}:{payment.order_id}:{payment.amount}".encode()
    ).hexdigest()

    payment = await mark_payment_paid(db, payment_id, signature)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    event_data = {
        "payment_id": payment.payment_id,
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": float(payment.amount),
        "currency": payment.currency,
        "paid_at": payment.paid_at.isoformat() + "Z" if payment.paid_at else None,
        "signature": payment.signature,
    }

    try:
        await publish_payment_event(rmq, "payment.completed", event_data)
    except Exception as e:
        print(f"RabbitMQ publish error: {e}")

    record_domain_event("payment_paid")
    return event_data


@app.post("/payments/{payment_id}/fail", response_model=PaymentStatusResponse)
async def fail_payment_endpoint(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    rmq: aio_pika.RobustConnection = Depends(get_rmq),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    existing_payment = await get_payment_by_payment_id(db, payment_id)
    if not existing_payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    ensure_payment_owner(existing_payment.customer_email, current_user)
    if existing_payment.status == "failed":
        return payment_status_payload(existing_payment)
    if existing_payment.status == "paid":
        raise HTTPException(status_code=400, detail="Payment already paid")

    payment = await mark_payment_failed(db, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    event_data = {
        "payment_id": payment.payment_id,
        "order_id": payment.order_id,
        "status": payment.status,
        "amount": float(payment.amount),
        "currency": payment.currency,
        "paid_at": None,
        "signature": None,
    }

    try:
        await publish_payment_event(rmq, "payment.failed", event_data)
    except Exception as e:
        print(f"RabbitMQ publish error: {e}")

    record_domain_event("payment_failed")
    return payment_status_payload(payment)
