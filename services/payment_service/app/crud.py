import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment
from app.schemas import PaymentCreate


async def create_payment(
    db: AsyncSession,
    payload: PaymentCreate,
    customer_email: str,
) -> Payment:
    payment = Payment(
        payment_id=f"pay_{uuid.uuid4().hex[:8]}",
        order_id=payload.order_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        description=payload.description,
        customer_email=customer_email,
        success_url=str(payload.success_url),
        fail_url=str(payload.fail_url),
        webhook_url=str(payload.webhook_url),
        status="pending",
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment


async def get_payment_by_payment_id(db: AsyncSession, payment_id: str) -> Payment | None:
    result = await db.execute(select(Payment).where(Payment.payment_id == payment_id))
    return result.scalar_one_or_none()


async def mark_payment_paid(db: AsyncSession, payment_id: str, signature: str) -> Payment | None:
    payment = await get_payment_by_payment_id(db, payment_id)
    if not payment:
        return None
    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    payment.signature = signature
    await db.commit()
    await db.refresh(payment)
    return payment


async def mark_payment_failed(db: AsyncSession, payment_id: str) -> Payment | None:
    payment = await get_payment_by_payment_id(db, payment_id)
    if not payment:
        return None
    payment.status = "failed"
    await db.commit()
    await db.refresh(payment)
    return payment
