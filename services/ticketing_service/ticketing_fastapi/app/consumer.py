import asyncio
import json
import logging
import os

from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import select

from . import models
from .broker import RabbitMQBroker
from .database import SessionLocal
from .schemas import BookingStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

RECONNECT_DELAY_SECONDS = 5
PAYMENTS_EXCHANGE = os.getenv("PAYMENTS_EXCHANGE", "payments")
PAYMENT_EVENTS_QUEUE = os.getenv("PAYMENT_EVENTS_QUEUE", "ticketing.payment.events")
PAYMENT_ROUTING_KEY = os.getenv("PAYMENT_ROUTING_KEY", "payment.*")


async def apply_payment_event(event_type: str, payload: dict) -> None:
    booking_id = int(payload["order_id"])
    payment_id = payload.get("payment_id")

    async with SessionLocal() as db:
        booking_result = await db.execute(
            select(models.Booking).where(models.Booking.id == booking_id)
        )
        booking = booking_result.scalar_one_or_none()
        if not booking:
            logger.warning("Бронирование id=%s из события оплаты не найдено", booking_id)
            return

        if booking.payment_reference and payment_id and booking.payment_reference != payment_id:
            logger.warning(
                "Пропуск события оплаты %s: booking id=%s привязан к payment_reference=%s",
                payment_id,
                booking.id,
                booking.payment_reference,
            )
            return

        if payment_id and not booking.payment_reference:
            booking.payment_reference = payment_id

        status = payload.get("status")
        is_completed = event_type == "payment.completed" or status == "paid"
        is_failed = event_type == "payment.failed" or status == "failed"

        if is_completed:
            if booking.status == BookingStatus.pending_payment.value:
                booking.status = BookingStatus.confirmed.value
                await db.commit()
                logger.info("Бронирование id=%s подтверждено оплатой %s", booking_id, payment_id)
            else:
                current_status = booking.status
                await db.commit()
                logger.info(
                    "Повторное payment.completed для booking id=%s со статусом %s",
                    booking_id,
                    current_status,
                )
            return

        if is_failed:
            if booking.status == BookingStatus.pending_payment.value:
                booking.status = BookingStatus.cancelled.value
                await db.commit()
                logger.info("Бронирование id=%s отменено после payment.failed", booking_id)
            else:
                current_status = booking.status
                await db.commit()
                logger.info(
                    "Повторное payment.failed для booking id=%s со статусом %s",
                    booking_id,
                    current_status,
                )
            return

        logger.warning("Неизвестное событие оплаты '%s': %s", event_type, payload)


async def handle_message(message: AbstractIncomingMessage) -> None:
    try:
        payload = json.loads(message.body.decode("utf-8"))
        event_type = message.routing_key or payload.get("event_type", "unknown")
        await apply_payment_event(event_type, payload)
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("Отклонено некорректное событие оплаты: %s", exc)
        await message.reject(requeue=False)
        return
    except Exception:
        logger.exception("Ошибка обработки события оплаты, сообщение будет возвращено в очередь")
        await message.nack(requeue=True)
        return

    await message.ack()


async def run_consumer() -> None:
    local_broker = RabbitMQBroker()
    while True:
        try:
            await local_broker.connect()
            if local_broker.channel is None:
                raise RuntimeError("Канал RabbitMQ не инициализирован")

            exchange = await local_broker.channel.declare_exchange(
                PAYMENTS_EXCHANGE,
                ExchangeType.TOPIC,
                durable=True,
            )
            queue = await local_broker.channel.declare_queue(
                PAYMENT_EVENTS_QUEUE,
                durable=True,
            )
            await queue.bind(exchange, routing_key=PAYMENT_ROUTING_KEY)

            logger.info(
                "Консьюмер слушает exchange='%s', queue='%s', routing_key='%s'",
                PAYMENTS_EXCHANGE,
                PAYMENT_EVENTS_QUEUE,
                PAYMENT_ROUTING_KEY,
            )
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    await handle_message(message)
        except asyncio.CancelledError:
            logger.info("Консьюмер остановлен")
            break
        except Exception:
            logger.exception("Ошибка консьюмера, переподключение через %s сек", RECONNECT_DELAY_SECONDS)
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
        finally:
            await local_broker.close()


def main() -> None:
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
