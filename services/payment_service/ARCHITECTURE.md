# Payment Service — Архитектурная схема

> Диаграммы написаны в формате Mermaid — GitHub рендерит их автоматически.

---

## 1. Взаимодействие с пользователем (полный сценарий оплаты)

```mermaid
sequenceDiagram
    actor User as Пользователь
    participant B as Booking Service
    participant P as Payment Service
    participant DB as PostgreSQL
    participant MQ as RabbitMQ

    User->>B: Забронировать билет (order_id=42)
    B->>P: POST /payments { order_id, amount, ... }
    P->>DB: INSERT INTO payments (status='pending')
    DB-->>P: payment record
    P-->>B: { payment_id, payment_url, status='pending' }
    B-->>User: Перейдите по ссылке для оплаты

    User->>P: POST /payments/{id}/pay
    P->>DB: UPDATE payments SET status='paid', paid_at=now(), signature=SHA256(...)
    DB-->>P: updated record
    P->>MQ: publish → payments exchange, routing_key='payment.completed'
    P-->>User: { status='paid', signature }

    MQ-->>B: consume → payment.completed event
    B->>B: Обновить бронирование → status='confirmed'
```

---

## 2. Схема взаимодействия сервисов

```mermaid
graph TD
    User([Пользователь])
    B[Booking Service]
    P[Payment Service\nFastAPI :8000]
    DB[(PostgreSQL\n:5433)]
    MQ[RabbitMQ\n:5672 / :15672]

    User -->|HTTP| B
    B -->|REST POST /payments| P
    P -->|asyncpg| DB
    P -->|aio_pika publish| MQ
    MQ -->|consume payment.*| B

    style P fill:#4a9eff,color:#fff
    style MQ fill:#ff6b35,color:#fff
    style DB fill:#2ecc71,color:#fff
```

---

## 3. Внутренняя структура Payment Service

```mermaid
graph TD
    subgraph FastAPI App
        EP1[POST /payments\ncreate_payment_endpoint]
        EP2[GET /payments/id\nget_payment_endpoint]
        EP3[POST /payments/id/pay\npay_payment_endpoint]
        EP4[POST /payments/id/fail\nfail_payment_endpoint]
    end

    subgraph Dependencies
        GDB[get_db\nAsyncSession]
        GRMQ[get_rmq\nRobustConnection]
    end

    subgraph CRUD app/crud.py
        C1[create_payment]
        C2[get_payment_by_payment_id]
        C3[mark_payment_paid]
        C4[mark_payment_failed]
    end

    subgraph Broker app/broker/publisher.py
        PUB[publish_payment_event\nrouting_key: payment.completed\nrouting_key: payment.failed]
    end

    subgraph DB app/db.py
        ENG[create_async_engine\nasyncpg driver]
        SES[async_sessionmaker]
    end

    EP1 --> GDB --> C1 --> ENG
    EP2 --> GDB --> C2 --> ENG
    EP3 --> GDB --> C3 --> ENG
    EP3 --> GRMQ --> PUB
    EP4 --> GDB --> C4 --> ENG
    EP4 --> GRMQ --> PUB
    ENG --> SES
```

---

## 4. Схема базы данных

```mermaid
erDiagram
    PAYMENTS {
        int         id              PK  "autoincrement"
        varchar50   payment_id      UK  "pay_xxxxxxxx, indexed"
        int         order_id            "indexed, FK к Booking"
        numeric     amount              "10 precision, 2 scale"
        varchar3    currency            "RUB, USD, ..."
        varchar255  description
        varchar255  customer_email
        varchar500  success_url
        varchar500  fail_url
        varchar500  webhook_url
        varchar20   status              "pending | paid | failed"
        varchar255  signature       NULL "SHA-256, только для paid"
        datetime    paid_at         NULL "только для paid"
        datetime    created_at
        datetime    updated_at
    }
```

### Жизненный цикл статуса

```mermaid
stateDiagram-v2
    [*] --> pending : POST /payments\n(создание)
    pending --> paid : POST /payments/id/pay\n+ publish payment.completed
    pending --> failed : POST /payments/id/fail\n+ publish payment.failed
    paid --> [*]
    failed --> [*]
```

---

## 5. RabbitMQ: потоки сообщений

```mermaid
graph LR
    P[Payment Service\nPublisher]

    subgraph RabbitMQ
        EX{{Exchange: payments\ntype: topic\ndurable: true}}
        Q1[Queue: booking_events\ndurable]
    end

    B[Booking Service\nConsumer]

    P -->|routing_key: payment.completed| EX
    P -->|routing_key: payment.failed| EX
    EX -->|binding: payment.*| Q1
    Q1 --> B
```

**Формат сообщения:**
```json
{
  "payment_id": "pay_a1b2c3d4",
  "order_id": 42,
  "status": "paid",
  "amount": 1500.00,
  "currency": "RUB",
  "paid_at": "2026-04-25T12:00:00Z",
  "signature": "<sha256>"
}
```

---

## 6. Docker — схема сети контейнеров

```mermaid
graph TD
    subgraph docker-compose network
        DB[payment_db\npostgres:16\nport 5433:5432]
        MQ[payment_rabbitmq\nrabbitmq:3.13-management\nport 5672, 15672]
        SVC[payment_service\nuvicorn :8000\nport 8000:8000]
    end

    Host([Хост / Booking Service])

    DB -->|healthcheck: pg_isready| SVC
    MQ -->|healthcheck: rabbitmq-diagnostics ping| SVC
    Host -->|HTTP :8000| SVC
    Host -->|AMQP :5672| MQ
    Host -->|Management UI :15672| MQ
```

**Порядок старта:**
1. `payment_db` — ждёт `pg_isready`
2. `payment_rabbitmq` — ждёт `rabbitmq-diagnostics ping`
3. `payment_service` — стартует только когда оба healthy → запускает `alembic upgrade head` → запускает `uvicorn`

---

## 7. Async: как работает event loop

```
Запрос 1: POST /pay  ──►  await db.execute()  ──► (ждёт БД, event loop свободен)
                                                         │
Запрос 2: GET /health ──────────────────────────────────┘  обрабатывается параллельно
                                                         │
Запрос 1: ◄────────────────────────────────── db вернул ответ, продолжаем
          await publish_payment_event()  ──►  (ждёт RabbitMQ, event loop свободен)
```

Ключевой принцип: `await` не блокирует поток. Пока один запрос ждёт ответа от БД или RabbitMQ, event loop переключается на другие запросы. Один процесс обрабатывает тысячи соединений.
