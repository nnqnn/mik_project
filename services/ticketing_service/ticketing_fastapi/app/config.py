import os


class Settings:
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret")
    AUTH_TOKEN_URL = os.getenv("AUTH_TOKEN_URL", "http://auth-api:8000/token")
    AUTH_TOKEN_SWAGGER_URL = os.getenv(
        "AUTH_TOKEN_SWAGGER_URL",
        "http://localhost:8003/token",
    )
    PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8000")
    TICKETING_PUBLIC_BASE_URL = os.getenv("TICKETING_PUBLIC_BASE_URL", "http://localhost:8001")
    MONOLITH_API_BASE_URL = os.getenv("MONOLITH_API_BASE_URL", "http://localhost:8000")
    MONOLITH_TIMEOUT_SECONDS = float(os.getenv("MONOLITH_TIMEOUT_SECONDS", "5"))


settings = Settings()
