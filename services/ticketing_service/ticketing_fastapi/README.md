# Ticketing Service

FastAPI-сервис бронирования билетов. В общем проекте он принимает JWT из Auth Service, создаёт бронь и синхронно создаёт платёж в Payment Service.

## Запуск

Рекомендуемый запуск всех сервисов из корня проекта:

```bash
docker compose up --build
```

Swagger: http://localhost:8001/docs

## Основной сценарий

1. Получить JWT в Auth Service.
2. В Swagger Ticketing нажать `Authorize` и вставить токен.
3. Вызвать `POST /bookings` с `match_id` и `quantity`.
4. Получить `payment_id` и `payment_url`.
5. После `payment.completed` из RabbitMQ consumer переведёт бронь в `confirmed`.
6. После `payment.failed` consumer переведёт pending-бронь в `cancelled` и вернёт места.

`GET /matches/{matchId}/availability` публичный. Остальные booking endpoints требуют Bearer JWT.
