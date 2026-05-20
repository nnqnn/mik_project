import json

import aio_pika

EXCHANGE_NAME = "payments"


async def publish_payment_event(
    connection: aio_pika.RobustConnection,
    routing_key: str,
    data: dict,
) -> None:
    async with connection.channel() as channel:
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(data).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )
