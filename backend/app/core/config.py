import os

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/attendance_register"
    JWT_SECRET_KEY: str = "change_me_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_URL: str = "http://localhost:5173"

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "Attendance Register Platform"
    SMTP_USE_TLS: bool = True

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        value = value.strip()
        # Render commonly provides postgresql://. SQLAlchemy needs an explicit driver.
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value[len("postgres://"):]
        elif value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value[len("postgresql://"):]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self):
        is_render = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID"))
        production = self.ENVIRONMENT.lower() in {"production", "prod"} or is_render
        if production and ("localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL):
            raise ValueError("Production DATABASE_URL must point to the managed Render PostgreSQL database, not localhost.")
        if production and self.JWT_SECRET_KEY == "change_me_in_production":
            raise ValueError("JWT_SECRET_KEY must be configured in Render environment variables.")
        return self


settings = Settings()
