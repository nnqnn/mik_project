from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class BookingStatus(str, Enum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"


class BookingCreate(BaseModel):
    match_id: int = Field(..., description="ID матча", examples=[101])
    quantity: int = Field(..., description="Количество билетов", ge=1, examples=[2])
    customer_name: str | None = Field(
        default=None,
        description="ФИО клиента. Если не передано, берётся из JWT.",
        max_length=255,
    )
    seats_available: int | None = Field(
        default=None,
        description="Fallback: доступные места с монолита, если Ticketing не может обратиться к нему напрямую.",
        ge=0,
    )
    unit_price: Decimal | None = Field(
        default=None,
        description="Fallback: цена билета с монолита, если Ticketing не может обратиться к нему напрямую.",
        ge=0,
    )
    currency: str | None = Field(
        default=None,
        description="Fallback: валюта цены билета.",
        min_length=3,
        max_length=3,
    )
    match_status: str | None = Field(
        default=None,
        description="Fallback: статус матча с монолита.",
        max_length=20,
    )


class BookingConfirm(BaseModel):
    payment_reference: str | None = Field(
        default=None,
        description="Идентификатор внешнего платежа",
        max_length=255,
        examples=["pay_abc123"],
    )


class BookingOut(BaseModel):
    id: int = Field(..., description="Уникальный идентификатор бронирования")
    match_id: int = Field(..., description="ID матча")
    customer_name: str = Field(..., description="ФИО клиента")
    customer_email: EmailStr = Field(..., description="Email клиента")
    quantity: int = Field(..., description="Количество билетов")
    unit_price: float = Field(..., description="Цена за билет")
    total_price: float = Field(..., description="Итоговая стоимость всех билетов")
    currency: str = Field(..., description="Код валюты ISO")
    status: BookingStatus = Field(..., description="Текущий статус бронирования")
    reserved_at: datetime = Field(..., description="Время создания бронирования")
    expires_at: datetime = Field(..., description="Время истечения бронирования")
    payment_reference: str | None = Field(
        default=None, description="Идентификатор внешнего платежа"
    )


class BookingWithPaymentOut(BookingOut):
    payment_id: str = Field(..., description="Идентификатор созданного платежа")
    payment_url: str = Field(..., description="Ссылка на оплату")
    payment_status: str = Field(..., description="Статус созданного платежа")


class AvailabilityOut(BaseModel):
    match_id: int = Field(..., description="ID матча")
    available_seats: int = Field(..., description="Количество доступных мест")
    unit_price: float = Field(..., description="Цена за билет")
    currency: str = Field(..., description="Код валюты ISO")
    can_reserve: bool = Field(..., description="Можно ли создать бронирование")


class ErrorOut(BaseModel):
    error: str = Field(..., description="Описание ошибки")
    code: int = Field(..., description="HTTP-код ошибки")
    details: str | None = Field(default=None, description="Детали ошибки")
