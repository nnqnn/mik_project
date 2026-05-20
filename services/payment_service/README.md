# Payment Service — GoroXcore

Микросервис оплаты учебного проекта **GoroXcore** (Django-монолит + 3 микросервиса).

**Стек:** FastAPI · SQLAlchemy 2.0 (async) · asyncpg · Alembic · aio-pika (RabbitMQ) · PostgreSQL · JWT · Docker

---

## Архитектура взаимодействия

```
Booking Service  ──REST + Bearer JWT──►  Payment Service  ──RabbitMQ──►  Booking Service
                 POST /payments                 payment.completed
                 ◄── payment_url              payment.failed
```

**Почему именно так:**

- Booking вызывает Payment синхронно через REST с Bearer JWT — потому что ему нужно сразу получить `payment_url` и отдать его пользователю.
- Payment уведомляет Booking асинхронно через RabbitMQ — потому что Payment не знает адрес Booking-сервиса, и не должен знать. Он просто публикует событие в очередь.

---

## Что было переделано и почему

### 1. Асинхронная работа с базой данных (`app/db.py`)

**Было:** синхронный `create_engine` + обычные сессии.

**Стало:**
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(settings.DATABASE_URL, echo=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

**Зачем:**  
FastAPI работает на `asyncio`. Если делать синхронные запросы к БД внутри `async def`-эндпоинта, весь event loop блокируется — сервер перестаёт обрабатывать другие запросы, пока не завершится запрос к БД.  
`create_async_engine` + `asyncpg` (драйвер) позволяют делать запросы к PostgreSQL без блокировки event loop. Сервер может параллельно обслуживать тысячи соединений.

**Драйвер в DATABASE_URL:** `postgresql+asyncpg://...` (не `postgresql://...`)

---

### 2. Асинхронные CRUD-функции (`app/crud.py`)

Все функции стали `async def` и используют `await`:

```python
async def create_payment(db: AsyncSession, payload: PaymentCreate) -> Payment:
    ...
    await db.commit()
    await db.refresh(payment)
    return payment

async def get_payment_by_payment_id(db: AsyncSession, payment_id: str) -> Payment | None:
    result = await db.execute(select(Payment).where(Payment.payment_id == payment_id))
    return result.scalar_one_or_none()
```

`select()` вместо `db.query()` — это SQLAlchemy 2.0 Core-стиль, совместимый с async.  
`scalar_one_or_none()` — возвращает объект или `None` (не кидает исключение, если не нашёл).

---

### 3. Миграции через Alembic (`alembic/`)

**Было:** `Base.metadata.create_all(engine)` при старте — таблицы создавались напрямую.

**Стало:** Alembic — инструмент для версионированных миграций.

**Зачем:**  
`create_all` не умеет обновлять уже существующую схему. Если добавить новое поле в модель — таблица в БД не изменится. Alembic хранит историю изменений схемы и может накатывать/откатывать версии.

**Структура:**
```
alembic/
├── env.py           # настройки Alembic (подключение к БД, импорт моделей)
└── versions/
    └── 0001_initial.py   # первая миграция — создаёт таблицу payments
```

**`alembic/env.py`** настроен на async:
```python
import asyncio
from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

def run_migrations_online():
    connectable = async_engine_from_config(...)
    asyncio.run(run_async_migrations(connectable))
```

**Запуск миграций:**
```bash
alembic upgrade head   # применить все миграции
alembic downgrade -1   # откатить последнюю
```

В `Dockerfile` миграции запускаются автоматически перед стартом сервера:
```
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### 4. RabbitMQ — брокер сообщений

#### Что такое брокер сообщений

RabbitMQ — это посредник между сервисами. Один сервис (Publisher) кладёт сообщение в очередь. Другой сервис (Consumer) читает из очереди в своё время. Они не знают друг о друге и не ждут друг друга.

```
Payment Service         RabbitMQ              Booking Service
  (Publisher)    ──►  [ exchange ]  ──►  [ queue ]  ──►  (Consumer)
                        payments              booking_events
                        topic
```

#### Exchange и Routing Key

Используется **topic exchange** `payments`. Topic exchange маршрутизирует сообщения по routing key:

| Событие | Routing Key | Когда публикуется |
|---------|-------------|-------------------|
| Оплата прошла | `payment.completed` | `POST /payments/{id}/pay` |
| Оплата отклонена | `payment.failed` | `POST /payments/{id}/fail` |

Booking-сервис подписывается на паттерн `payment.*` — и получает оба события.

#### Реализация: `app/broker/publisher.py`

```python
async def publish_payment_event(
    connection: aio_pika.RobustConnection,
    routing_key: str,   # "payment.completed" или "payment.failed"
    data: dict,
) -> None:
    async with connection.channel() as channel:
        exchange = await channel.declare_exchange(
            "payments",
            aio_pika.ExchangeType.TOPIC,
            durable=True,  # exchange переживёт перезапуск RabbitMQ
        )
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(data).encode(),
                content_type="application/json",
            ),
            routing_key=routing_key,
        )
```

`durable=True` — exchange сохраняется на диск. После перезапуска RabbitMQ он не исчезнет.  
`aio_pika` — асинхронная библиотека для RabbitMQ, не блокирует event loop.

#### Управление соединением: lifespan (`app/main.py`)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте сервера — открыть одно соединение с RabbitMQ
    app.state.rmq_connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    yield
    # При остановке сервера — закрыть соединение
    await app.state.rmq_connection.close()
```

**Зачем одно соединение на весь lifecycle:**  
Открывать новое соединение с RabbitMQ на каждый запрос — дорого (TCP handshake + аутентификация). `connect_robust` открывает одно соединение при старте и автоматически переподключается, если RabbitMQ перезапустился.

#### Dependency для передачи соединения в эндпоинты

```python
def get_rmq(request: Request) -> aio_pika.RobustConnection:
    return request.app.state.rmq_connection

@app.post("/payments/{payment_id}/pay")
async def pay_payment_endpoint(
    payment_id: str,
    db: AsyncSession = Depends(get_db),
    rmq: aio_pika.RobustConnection = Depends(get_rmq),  # ← инжектируем соединение
):
    ...
    await publish_payment_event(rmq, "payment.completed", event_data)
```

#### Что содержит событие

```json
{
  "payment_id": "pay_a1b2c3d4",
  "order_id": 42,
  "status": "paid",
  "amount": 1500.00,
  "currency": "RUB",
  "paid_at": "2026-04-25T12:00:00Z",
  "signature": "sha256-хеш"
}
```

`signature` — SHA-256 хеш строки `payment_id:order_id:amount`. Booking-сервис может проверить подлинность события.

---

### 5. Docker Compose (`docker-compose.yml`)

Запускает три контейнера:

```
payment_db (postgres:16)   ──healthcheck──►
payment_rabbitmq           ──healthcheck──►   payment_service
```

`condition: service_healthy` гарантирует: payment-service стартует только после того, как БД и RabbitMQ реально готовы принимать соединения (не просто запустились).

---

## Структура проекта

```
payment-service/
├── app/
│   ├── main.py          # FastAPI app, эндпоинты, lifespan
│   ├── models.py        # SQLAlchemy модель Payment
│   ├── schemas.py       # Pydantic схемы (валидация запросов/ответов)
│   ├── crud.py          # async CRUD-операции с БД
│   ├── db.py            # async engine, сессия, Base
│   ├── config.py        # настройки через pydantic-settings (.env)
│   └── broker/
│       ├── __init__.py
│       └── publisher.py # публикация событий в RabbitMQ
├── alembic/
│   ├── env.py           # async настройки Alembic
│   └── versions/
│       └── 0001_initial.py
├── alembic.ini
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env                 # не коммитить в git
```

---

## Запуск

Для запуска всех связанных микросервисов используйте compose из корня проекта:

```bash
docker compose up --build
```

Payment Swagger в общем compose доступен на `http://localhost:8002/docs`.

Standalone-запуск только Payment Service:

```bash
cd ~/PROJECTS/Python/GoroXcore/payment-service
docker compose up --build
```

| Сервис | URL |
|--------|-----|
| Swagger UI | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |
| RabbitMQ Management | http://localhost:15672 (guest/guest) |

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/payments` | Создать платёж, получить `payment_url` |
| `GET` | `/payments/{id}` | Статус платежа |
| `POST` | `/payments/{id}/pay` | Пометить оплаченным → публикует `payment.completed` |
| `POST` | `/payments/{id}/fail` | Пометить отклонённым → публикует `payment.failed` |

Все `/payments/*` эндпоинты требуют `Authorization: Bearer <jwt>` из Auth Service. Email плательщика берётся из JWT и не передаётся в теле запроса. `GET /health` публичный.

### Пример: создать платёж

```bash
curl -X POST http://localhost:8000/payments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "order_id": 42,
    "amount": 1500.00,
    "currency": "RUB",
    "description": "Билеты на матч",
    "success_url": "http://booking/success",
    "fail_url": "http://booking/fail",
    "webhook_url": "http://booking/webhook"
  }'
```

Ответ:
```json
{
  "payment_id": "pay_a1b2c3d4",
  "status": "pending",
  "order_id": 42,
  "amount": 1500.00,
  "currency": "RUB",
  "payment_url": "http://localhost:8002/payments/pay_a1b2c3d4",
  "created_at": "2026-04-25T12:00:00"
}
```

---

## Для Booking Service (как интегрировать)

1. Вызвать `POST /payments` — получить `payment_url`, отдать пользователю.
2. Подписаться на RabbitMQ exchange `payments` с паттерном `payment.*`.
3. При получении `payment.completed` — обновить статус бронирования на `confirmed`.
4. При получении `payment.failed` — обновить статус на `cancelled`.

```python
# Пример Consumer на стороне Booking (aio_pika)
async with connection.channel() as channel:
    exchange = await channel.declare_exchange("payments", ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue("booking_payment_events", durable=True)
    await queue.bind(exchange, routing_key="payment.*")

    async with queue.iterator() as messages:
        async for message in messages:
            async with message.process():
                data = json.loads(message.body)
                # обработать data["status"] == "paid" / "failed"
```
