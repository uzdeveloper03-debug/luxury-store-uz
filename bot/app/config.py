from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parents[2]


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env.bot",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: SecretStr
    webapp_url: str
    support_url: str = "https://t.me/luxurystore_support"

    @field_validator("webapp_url", "support_url")
    @classmethod
    def validate_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Нужен корректный публичный HTTPS-адрес")
        return value.rstrip("/")


@lru_cache
def get_settings() -> BotSettings:
    return BotSettings()
