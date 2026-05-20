from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import os

import httpx
from fastapi import Body, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models, schemas
from .broker import broker
from .config import settings
from .database import SessionLocal, ensure_schema
from .metrics import metrics_middleware, metrics_response, record_domain_event
from .monolith import (
    MonolithDataError,
    MonolithUnavailableError,
    fetch_match_ticketing_info,
)
from .security import get_current_user

logger = logging.getLogger(__name__)

PAYMENT_TIMEOUT_SECONDS = 10.0
ACTIVE_BOOKING_STATUSES = {
    schemas.BookingStatus.pending_payment.value,
    schemas.BookingStatus.confirmed.value,
}

app = FastAPI(
    title="Ticketing Service API",
    description=(
        "Сервис бронирования билетов на матчи. Пользовательские операции "
        "требуют JWT, а создание бронирования сразу создаёт платёж."
    ),
    version="1.0.0",
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


async def get_db():
    async with SessionLocal() as db:
        yield db


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()


@app.on_event("startup")
async def on_startup():
    # Make startup deterministic even when local sqlite volume is new/old.
    ensure_schema()
    try:
        await broker.connect()
    except Exception:
        logger.exception("RabbitMQ недоступен на старте. API продолжит работу без брокера.")


@app.on_event("shutdown")
async def on_shutdown():
    await broker.close()


def error_response(status_code: int, message: str, details: str | None = None):
    payload = {"error": message, "code": status_code}
    if details:
        payload["details"] = details
    return JSONResponse(status_code=status_code, content=payload)


def parse_int(value: str, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} должен быть целым числом")


def booking_to_out(booking: models.Booking) -> dict:
    return {
        "id": booking.id,
        "match_id": booking.match_id,
        "customer_name": booking.customer_name,
        "customer_email": booking.customer_email,
        "quantity": booking.quantity,
        "unit_price": float(booking.unit_price),
        "total_price": float(booking.total_price),
        "currency": booking.currency,
        "status": booking.status,
        "reserved_at": booking.reserved_at,
        "expires_at": booking.expires_at,
        "payment_reference": booking.payment_reference,
    }


def availability_to_out(match_info: dict, reserved_seats: int) -> dict:
    available = max(match_info["seats_available"] - reserved_seats, 0)
    return {
        "match_id": match_info["match_id"],
        "available_seats": available,
        "unit_price": float(match_info["unit_price"]),
        "currency": match_info["currency"],
        "can_reserve": available > 0,
    }


def booking_event_payload(booking: models.Booking) -> dict:
    return {
        "id": booking.id,
        "match_id": booking.match_id,
        "customer_email": booking.customer_email,
        "quantity": booking.quantity,
        "status": booking.status,
        "total_price": float(booking.total_price),
        "currency": booking.currency,
        "payment_reference": booking.payment_reference,
        "reserved_at": booking.reserved_at.isoformat() if booking.reserved_at else None,
        "expires_at": booking.expires_at.isoformat() if booking.expires_at else None,
    }


def user_display_name(current_user: dict) -> str:
    parts = [
        str(current_user.get("first_name") or "").strip(),
        str(current_user.get("last_name") or "").strip(),
    ]
    name = " ".join(part for part in parts if part)
    return name or str(current_user["email"])


def ensure_email_allowed(email: str, current_user: dict) -> bool:
    return email.lower() == str(current_user["email"]).lower()


def booking_with_payment_to_out(booking: models.Booking, payment_data: dict) -> dict:
    payload = booking_to_out(booking)
    payload.update(
        {
            "payment_id": payment_data["payment_id"],
            "payment_url": payment_data["payment_url"],
            "payment_status": payment_data["status"],
        }
    )
    return payload


def fallback_match_info_from_payload(payload: schemas.BookingCreate) -> dict | None:
    if payload.seats_available is None or payload.unit_price is None:
        return None
    return {
        "match_id": payload.match_id,
        "seats_available": max(int(payload.seats_available), 0),
        "unit_price": Decimal(str(payload.unit_price)),
        "currency": payload.currency or "RUB",
        "status": payload.match_status,
    }


async def create_payment_for_booking(booking: models.Booking, access_token: str) -> dict:
    base_url = settings.TICKETING_PUBLIC_BASE_URL.rstrip("/")
    payment_payload = {
        "order_id": booking.id,
        "amount": str(booking.total_price),
        "currency": booking.currency,
        "description": f"Tickets for match {booking.match_id}",
        "success_url": f"{base_url}/bookings/{booking.id}",
        "fail_url": f"{base_url}/bookings/{booking.id}",
        "webhook_url": f"{base_url}/bookings/{booking.id}/confirm",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    payment_url = f"{settings.PAYMENT_SERVICE_URL.rstrip('/')}/payments"

    async with httpx.AsyncClient(timeout=PAYMENT_TIMEOUT_SECONDS) as client:
        response = await client.post(payment_url, json=payment_payload, headers=headers)

    if response.status_code >= 400:
        raise RuntimeError(f"Payment service returned {response.status_code}: {response.text}")

    data = response.json()
    required_fields = {"payment_id", "payment_url", "status"}
    missing_fields = required_fields - set(data)
    if missing_fields:
        raise RuntimeError(f"Payment service response missing fields: {sorted(missing_fields)}")
    return data


async def get_reserved_seats(db: AsyncSession, match_id: int) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(models.Booking.quantity), 0)).where(
            models.Booking.match_id == match_id,
            models.Booking.status.in_(ACTIVE_BOOKING_STATUSES),
        )
    )
    return int(result.scalar_one() or 0)


def flatten_validation_errors(errors: list[dict]) -> str:
    parts = []
    for err in errors:
        loc = ".".join(str(item) for item in err.get("loc", []))
        msg = err.get("msg", "")
        if loc:
            parts.append(f"{loc}: {msg}")
        else:
            parts.append(msg)
    return "; ".join(parts) if parts else "Некорректные данные запроса"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(
        400,
        "Некорректные данные запроса",
        details=flatten_validation_errors(exc.errors()),
    )


@app.get(
    "/bookings",
    summary="Список бронирований",
    description="Возвращает массив бронирований билетов.",
    response_model=list[schemas.BookingOut],
    responses={400: {"model": schemas.ErrorOut}},
)
async def list_bookings(
    matchId: str | None = Query(default=None, description="Фильтр по идентификатору матча."),
    status: str | None = Query(default=None, description="Фильтр по статусу бронирования."),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(models.Booking).order_by(models.Booking.reserved_at.desc())

    if matchId is not None:
        try:
            match_id = parse_int(matchId, "matchId")
        except ValueError as exc:
            return error_response(400, "Некорректные данные запроса", str(exc))
        query = query.where(models.Booking.match_id == match_id)

    if status:
        allowed = {item.value for item in schemas.BookingStatus}
        if status not in allowed:
            return error_response(400, "Некорректные данные запроса", "Неизвестный статус")
        query = query.where(models.Booking.status == status)

    query = query.where(models.Booking.customer_email == current_user["email"])

    result = await db.execute(query)
    bookings = result.scalars().all()
    return [booking_to_out(booking) for booking in bookings]


@app.post(
    "/bookings",
    summary="Создать бронирование",
    description="Создаёт бронирование билетов на матч и платёж для него.",
    response_model=schemas.BookingWithPaymentOut,
    status_code=201,
    responses={
        400: {"model": schemas.ErrorOut},
        409: {"model": schemas.ErrorOut},
        503: {"model": schemas.ErrorOut},
    },
)
async def create_booking(
    payload: schemas.BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        match_info = await fetch_match_ticketing_info(payload.match_id)
    except MonolithDataError as exc:
        match_info = fallback_match_info_from_payload(payload)
        if not match_info:
            logger.exception("Монолит вернул некорректные данные по матчу id=%s", payload.match_id)
            return error_response(503, "Монолит недоступен", "Некорректные данные матча")
        logger.warning(
            "Используем данные матча id=%s из запроса: монолит вернул некорректные данные (%s)",
            payload.match_id,
            exc,
        )
    except MonolithUnavailableError as exc:
        match_info = fallback_match_info_from_payload(payload)
        if not match_info:
            logger.exception("Не удалось получить данные матча id=%s из монолита", payload.match_id)
            return error_response(503, "Монолит недоступен", "Не удалось получить данные матча")
        logger.warning(
            "Используем данные матча id=%s из запроса: монолит недоступен (%s)",
            payload.match_id,
            exc,
        )

    if not match_info:
        return error_response(400, "Некорректные данные запроса", "match_id не найден")

    reserved_seats = await get_reserved_seats(db, payload.match_id)
    available = max(match_info["seats_available"] - reserved_seats, 0)
    if payload.quantity > available:
        details = f"Запрошено {payload.quantity}, доступно {available}"
        return error_response(409, "Недостаточно доступных мест", details)

    unit_price = Decimal(str(match_info["unit_price"]))
    total_price = unit_price * Decimal(str(payload.quantity))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    booking = models.Booking(
        match_id=payload.match_id,
        customer_name=payload.customer_name or user_display_name(current_user),
        customer_email=current_user["email"],
        quantity=payload.quantity,
        unit_price=unit_price,
        total_price=total_price,
        currency=match_info["currency"],
        status=schemas.BookingStatus.pending_payment.value,
        expires_at=expires_at,
    )

    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    try:
        payment_data = await create_payment_for_booking(booking, current_user["access_token"])
    except Exception:
        logger.exception("Не удалось создать платёж для бронирования id=%s", booking.id)
        booking.status = schemas.BookingStatus.cancelled.value
        await db.commit()
        await db.refresh(booking)
        await broker.publish("booking.cancelled", booking_event_payload(booking))
        record_domain_event("payment_create_failed")
        return error_response(
            503,
            "Сервис оплаты недоступен",
            "Бронирование отменено, места возвращены",
        )

    booking.payment_reference = payment_data["payment_id"]
    await db.commit()
    await db.refresh(booking)
    await broker.publish("booking.created", booking_event_payload(booking))
    record_domain_event("booking_created")
    return booking_with_payment_to_out(booking, payment_data)


@app.get(
    "/bookings/{bookingId}",
    summary="Получить бронирование по ID",
    response_model=schemas.BookingOut,
    responses={404: {"model": schemas.ErrorOut}},
)
async def get_booking(
    bookingId: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        booking_id = parse_int(bookingId, "bookingId")
    except ValueError as exc:
        return error_response(400, "Некорректные данные запроса", str(exc))

    booking_result = await db.execute(select(models.Booking).where(models.Booking.id == booking_id))
    booking = booking_result.scalar_one_or_none()
    if not booking:
        return error_response(404, "Ресурс не найден", "Бронирование не найдено")
    if not ensure_email_allowed(booking.customer_email, current_user):
        return error_response(403, "Доступ запрещён", "Бронирование принадлежит другому пользователю")
    return booking_to_out(booking)


@app.delete(
    "/bookings/{bookingId}",
    summary="Отменить бронирование",
    response_model=schemas.BookingOut,
    responses={404: {"model": schemas.ErrorOut}},
)
async def cancel_booking(
    bookingId: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        booking_id = parse_int(bookingId, "bookingId")
    except ValueError as exc:
        return error_response(400, "Некорректные данные запроса", str(exc))

    booking_result = await db.execute(select(models.Booking).where(models.Booking.id == booking_id))
    booking = booking_result.scalar_one_or_none()
    if not booking:
        return error_response(404, "Ресурс не найден", "Бронирование не найдено")
    if not ensure_email_allowed(booking.customer_email, current_user):
        return error_response(403, "Доступ запрещён", "Бронирование принадлежит другому пользователю")

    if booking.status not in [
        schemas.BookingStatus.cancelled.value,
        schemas.BookingStatus.expired.value,
    ]:
        booking.status = schemas.BookingStatus.cancelled.value
        await db.commit()
        await db.refresh(booking)
        await broker.publish("booking.cancelled", booking_event_payload(booking))
        record_domain_event("booking_cancelled")

    return booking_to_out(booking)


@app.post(
    "/bookings/{bookingId}/confirm",
    summary="Подтвердить бронирование",
    description="Подтверждает бронирование после внешней оплаты.",
    response_model=schemas.BookingOut,
    responses={400: {"model": schemas.ErrorOut}, 404: {"model": schemas.ErrorOut}},
)
async def confirm_booking(
    bookingId: str,
    payload: schemas.BookingConfirm | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    try:
        booking_id = parse_int(bookingId, "bookingId")
    except ValueError as exc:
        return error_response(400, "Некорректные данные запроса", str(exc))

    booking_result = await db.execute(select(models.Booking).where(models.Booking.id == booking_id))
    booking = booking_result.scalar_one_or_none()
    if not booking:
        return error_response(404, "Ресурс не найден", "Бронирование не найдено")
    if not ensure_email_allowed(booking.customer_email, current_user):
        return error_response(403, "Доступ запрещён", "Бронирование принадлежит другому пользователю")

    if booking.status in [
        schemas.BookingStatus.cancelled.value,
        schemas.BookingStatus.expired.value,
    ]:
        return error_response(400, "Некорректные данные запроса", "Бронирование не активно")

    if booking.status != schemas.BookingStatus.confirmed.value:
        booking.status = schemas.BookingStatus.confirmed.value
        if payload and payload.payment_reference:
            booking.payment_reference = payload.payment_reference
        await db.commit()
        await db.refresh(booking)
        await broker.publish("booking.confirmed", booking_event_payload(booking))
        record_domain_event("booking_confirmed")

    return booking_to_out(booking)


@app.get(
    "/matches/{matchId}/availability",
    summary="Проверить доступность билетов",
    response_model=schemas.AvailabilityOut,
    responses={404: {"model": schemas.ErrorOut}},
)
async def match_availability(matchId: str, db: AsyncSession = Depends(get_db)):
    try:
        match_id = parse_int(matchId, "matchId")
    except ValueError as exc:
        return error_response(400, "Некорректные данные запроса", str(exc))

    try:
        match_info = await fetch_match_ticketing_info(match_id)
    except MonolithDataError:
        logger.exception("Монолит вернул некорректные данные по матчу id=%s", match_id)
        return error_response(503, "Монолит недоступен", "Некорректные данные матча")
    except MonolithUnavailableError:
        logger.exception("Не удалось получить данные матча id=%s из монолита", match_id)
        return error_response(503, "Монолит недоступен", "Не удалось получить данные матча")

    if not match_info:
        return error_response(404, "Ресурс не найден", "Матч не найден")

    reserved_seats = await get_reserved_seats(db, match_id)
    return availability_to_out(match_info, reserved_seats)
