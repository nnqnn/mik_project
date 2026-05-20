import asyncio
import json

import aio_pika
from sqlalchemy.exc import IntegrityError

from . import broker, models
from .database import Base, SessionLocal, engine


def create_profile(payload: dict) -> None:
    db = SessionLocal()
    try:
        user_id = int(payload["user_id"])
        existing_profile = (
            db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        )
        if existing_profile:
            return
        profile = models.Profile(
            user_id=user_id,
            email=payload["email"],
            first_name=payload["first_name"],
            last_name=payload["last_name"],
        )
        db.add(profile)
        db.commit()
    except IntegrityError:
        db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def handle_message(message: aio_pika.IncomingMessage) -> None:
    try:
        payload = json.loads(message.body.decode("utf-8"))
        if payload.get("event_type") != broker.USER_REGISTERED_EVENT:
            raise ValueError("unsupported event_type")
        create_profile(payload)
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Rejecting invalid message: {exc}", flush=True)
        await message.reject(requeue=False)
        return
    except Exception as exc:
        print(f"Profile creation failed, requeueing message: {exc}", flush=True)
        await message.nack(requeue=True)
        return

    await message.ack()


async def main() -> None:
    Base.metadata.create_all(bind=engine)

    connection = await aio_pika.connect_robust(broker.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        _, queue = await broker.declare_topology(channel)
        await queue.consume(handle_message)
        print("Profile worker is listening for user.registered events", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
