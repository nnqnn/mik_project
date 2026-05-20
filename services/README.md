# MIK Project — связанные микросервисы

Проект состоит из трёх FastAPI-микросервисов:

- Auth Service — регистрация, login, JWT и профиль пользователя.
- Ticketing Service — бронирование билетов и проверка доступности мест.
- Payment Service — создание платежей, смена статуса оплаты и RabbitMQ-события.

## Запуск всего проекта

```bash
./scripts/ci_cd.sh deploy
```

После запуска:

| Сервис | URL |
| --- | --- |
| Django Monolith | http://localhost:8000 |
| Auth Swagger | http://localhost:8003/docs |
| Ticketing Swagger | http://localhost:8001/docs |
| Payment Swagger | http://localhost:8002/docs |
| RabbitMQ Management | http://localhost:15672 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

RabbitMQ credentials: `guest` / `guest`.
Grafana credentials: `admin` / `admin`.

## Локальный CI/CD

Из корня проекта:

```bash
./scripts/ci_cd.sh check
./scripts/ci_cd.sh build
./scripts/ci_cd.sh deploy
./scripts/ci_cd.sh down
```

`check` устанавливает зависимости в `.ci/venv`, запускает Django tests, pytest для
Auth/Ticketing/Payment и валидирует общий `services/docker-compose.yml`.

## Метрики

Prometheus собирает `/metrics` со всех API:

| Target | URL |
| --- | --- |
| Django | http://localhost:8000/metrics |
| Auth | http://localhost:8003/metrics |
| Ticketing | http://localhost:8001/metrics |
| Payment | http://localhost:8002/metrics |

Основные метрики: `mik_http_requests_total`,
`mik_http_request_duration_seconds`, `mik_domain_events_total`.

## Связанный сценарий

1. Зарегистрируйте пользователя в Auth: `POST http://localhost:8000/register`.
2. Скопируйте JWT или авторизуйтесь через Swagger `Authorize`.
3. В Ticketing создайте бронь: `POST http://localhost:8001/bookings`.
   - В теле нужны `match_id` и `quantity`.
   - Email пользователя берётся из JWT Auth Service.
   - В ответе придут `payment_id`, `payment_url`, `payment_status`.
4. В Payment вызовите `POST /payments/{payment_id}/pay` с тем же Bearer JWT.
5. Payment опубликует `payment.completed`, а `ticketing-payment-consumer` переведёт бронь в `confirmed`.

Для проверки отказа оплаты вызовите `POST /payments/{payment_id}/fail`; бронь перейдёт в `cancelled`, а места вернутся в доступность.

## Переменные окружения

- `JWT_SECRET_KEY` — общий секрет JWT для Auth, Ticketing и Payment.
- `RABBITMQ_URL` — адрес RabbitMQ внутри контейнеров.
- `AUTH_TOKEN_URL` — OAuth2 token URL для Swagger.
- `PAYMENT_SERVICE_URL` — внутренний URL Payment Service для Ticketing.
- `PAYMENT_PUBLIC_BASE_URL` — внешний URL Payment Service в ответах API.
- `DATABASE_URL` — строка подключения к БД конкретного сервиса.

По умолчанию compose использует `JWT_SECRET_KEY=change-this-secret`; для реальной среды задайте свой секрет.
