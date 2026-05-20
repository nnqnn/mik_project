from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl


class PaymentCreate(BaseModel):
    order_id: int
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    description: str
    success_url: HttpUrl
    fail_url: HttpUrl
    webhook_url: HttpUrl


class PaymentCreateResponse(BaseModel):
    payment_id: str
    status: str
    order_id: int
    amount: Decimal
    currency: str
    payment_url: str
    created_at: datetime


class PaymentStatusResponse(BaseModel):
    payment_id: str
    status: str
    order_id: int
    amount: Decimal
    currency: str
    paid_at: datetime | None = None
    signature: str | None = None
