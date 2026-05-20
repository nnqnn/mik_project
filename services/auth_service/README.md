# Auth Microservice (FastAPI + SQLite + JWT + RabbitMQ)

Небольшой сервис регистрации и авторизации. После регистрации пользователь создаётся в API, событие `user.registered` отправляется в RabbitMQ, а отдельный worker асинхронно создаёт профиль. JWT используется также Ticketing и Payment сервисами.

## Что есть
- FastAPI со Swagger UI (`/docs`) и OpenAPI (`/openapi.json`)
- SQLite база `app.db`, создаётся автоматически
- RabbitMQ как брокер сообщений
- Worker для асинхронного создания профиля
- Хеширование паролей (`bcrypt`)
- JWT токены (HS256) с claims `sub`, `user_id`, `email`, `first_name`, `last_name`

## Быстрый старт через Docker
Для запуска всех связанных микросервисов используйте compose из корня проекта:
```bash
docker compose up --build
```

Для standalone-запуска только Auth Service:
```bash
docker compose up --build
```

API будет доступен на `http://127.0.0.1:8000`, RabbitMQ Management UI — на `http://127.0.0.1:15672` (`guest` / `guest`).

## Локальный старт без Docker
Перед запуском API и worker должен быть доступен RabbitMQ по адресу из `RABBITMQ_URL`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# опционально: свои настройки
export JWT_SECRET_KEY="super-secret-key"
export DATABASE_URL="sqlite:///./app.db"
export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"

uvicorn app.main:app --reload
```

В отдельном терминале запустите worker:
```bash
source .venv/bin/activate
python3 -m app.worker
```

## Эндпоинты
### POST /register
- Тело: `email`, `password` (до 72 символов), `first_name`, `last_name`
- Результат: JWT токен; после создания пользователя публикуется событие для создания профиля
```bash
curl -X POST http://127.0.0.1:8000/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret123","first_name":"Ivan","last_name":"Ivanov"}'
```

### POST /login
- Тело: `email`, `password` (до 72 символов)
- Результат: уже существующий JWT токен
```bash
curl -X POST http://127.0.0.1:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret123"}'
```

### POST /token  (для кнопки Authorize в Swagger)
- Формат: `application/x-www-form-urlencoded`
- Поля: `username` (email), `password`
- Результат: JWT токен
```bash
curl -X POST http://127.0.0.1:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=secret123"
```

### GET /profiles/me
- Требуется авторизация: `Authorization: Bearer <token>`
- Результат: профиль текущего пользователя
- Если worker ещё не обработал событие регистрации, вернётся `404`
```bash
curl -H "Authorization: Bearer <token>" \
  http://127.0.0.1:8000/profiles/me
```

### GET /users
- Требуется авторизация: `Authorization: Bearer <token>`
- Параметры фильтрации (опционально, точное совпадение):
  - `user_id`
  - `email`
  - `first_name`
  - `last_name`
- Результат: список пользователей (id, email, first_name, last_name)
```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8000/users?email=user@example.com"
```

### PATCH /users/me
- Требуется авторизация: `Authorization: Bearer <token>`
- Тело (опционально): `first_name`, `last_name`, `password` (до 72 символов)
- Результат: обновлённый пользователь
```bash
curl -X PATCH http://127.0.0.1:8000/users/me \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"first_name":"New","last_name":"Name","password":"newpass123"}'
```

## Структура
```
app/
  broker.py      # RabbitMQ topology и публикация событий
  main.py        # эндпоинты и настройка FastAPI
  worker.py      # consumer, создающий профили
  auth.py        # JWT и хеширование паролей
  database.py    # подключение к SQLite
  models.py      # ORM-модели пользователя и профиля
  schemas.py     # Pydantic-схемы запросов/ответов
Dockerfile
docker-compose.yml
requirements.txt
README.md
```

## Переменные окружения
- `DATABASE_URL` — строка подключения SQLAlchemy, по умолчанию `sqlite:///./app.db`
- `RABBITMQ_URL` — адрес RabbitMQ, по умолчанию `amqp://guest:guest@localhost:5672/`
- `JWT_SECRET_KEY` — секрет для JWT, по умолчанию `change-this-secret`

## Заметки по безопасности
- В продакшене обязательно задайте переменную окружения `JWT_SECRET_KEY`.
- Подумайте про ротацию ключей, HTTPS и хранение паролей с дополнительными политиками сложности.
