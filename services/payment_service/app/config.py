from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    JWT_SECRET_KEY: str = "change-this-secret"
    AUTH_TOKEN_URL: str = "http://localhost:8000/token"
    AUTH_TOKEN_SWAGGER_URL: str = "http://localhost:8003/token"
    PAYMENT_PUBLIC_BASE_URL: str = "http://localhost:8002"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
