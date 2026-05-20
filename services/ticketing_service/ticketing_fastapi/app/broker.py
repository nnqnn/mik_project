import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from aio_pika import DeliveryMode, Message, connect_robust

logger = logging.getLogger(__name__)


class RabbitMQBroker:
    def __init__(self, url: str | None = None, queue_name: str | None = None) -> None:
        self.url = url or os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.queue_name = queue_name or os.getenv("RABBITMQ_QUEUE", "ticketing.events")
        self.connection = None
        self.channel = None
        self.queue = None

    async def connect(self) -> None:
        if (
            self.connection is not None
            and not self.connection.is_closed
            and self.channel is not None
            and not self.channel.is_closed
        ):
            return

        self.connection = await connect_robust(self.url)
        self.channel = await self.connection.channel()
        self.queue = await self.channel.declare_queue(self.queue_name, durable=True)
        logger.info("RabbitMQ подключён: queue=%s", self.queue_name)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> bool:
        try:
            await self.connect()
            if self.channel is None:
                return False

            body = json.dumps(
                {
                    "event_type": event_type,
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": payload,
                },
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")

            message = Message(
                body=body,
                content_type="application/json",
                delivery_mode=DeliveryMode.PERSISTENT,
                type=event_type,
            )
            await self.channel.default_exchange.publish(
                message, routing_key=self.queue_name
            )
            return True
        except Exception:
            logger.exception("Не удалось отправить событие '%s' в RabbitMQ", event_type)
            return False

    async def close(self) -> None:
        if self.channel is not None and not self.channel.is_closed:
            await self.channel.close()
        if self.connection is not None and not self.connection.is_closed:
            await self.connection.close()
        self.channel = None
        self.connection = None
        self.queue = None


broker = RabbitMQBroker()
