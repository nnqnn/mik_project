import json
import os
from typing import Any

import aio_pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
EXCHANGE_NAME = "user.events"
QUEUE_NAME = "profiles.user_registered"
USER_REGISTERED_EVENT = "user.registered"


async def declare_topology(channel):
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key=USER_REGISTERED_EVENT)
    return exchange, queue


async def publish_user_registered_event(payload: dict[str, Any]) -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    try:
        channel = await connection.channel(publisher_confirms=True)
        exchange, _ = await declare_topology(channel)
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            type=USER_REGISTERED_EVENT,
        )
        await exchange.publish(message, routing_key=USER_REGISTERED_EVENT)
    finally:
        await connection.close()
