from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .validation import (admin_password_problems, anchor_path, bot_token_problems,
                         environment_problems, is_inside, normalize_database_url,
                         secret_key_problems, sqlite_file_path)

BACKEND_DIR = Path(__file__).resolve().parents[2]  # .../backend
PROJECT_DIR = BACKEND_DIR.parent                   # корень проекта


class Settings(BaseSettings):
    # .env ищется по абсолютным путям — работает при запуске из любой папки.
    # Порядок: корень проекта, затем backend/ (последний файл приоритетнее).
    # Переменные окружения всегда приоритетнее файлов.
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8", extra="ignore", str_strip_whitespace=True,
        validate_default=True)  # валидаторы путей применяются и к значениям по умолчанию

    app_env: str = "development"  # development | test | production
    bot_token: str = ""
    database_url: str = "sqlite:///./luxury.db"
    secret_key: str = ""          # намеренно пустой: без явного значения приложение не стартует
    admin_username: str = "admin"
    admin_password: str = ""      # намеренно пустой: без явного значения приложение не стартует
    upload_dir: str = "./uploads"
    backup_dir: str = "./backups"
    backup_keep: int = Field(default=14, ge=1, le=1000)
    cors_origins: str = ""
    webapp_url: str = ""          # HTTPS-адрес Mini App; его origin автоматически разрешается в CORS
    debug: bool = False
    max_upload_mb: int = Field(default=5, ge=1, le=50)
    max_images_per_product: int = Field(default=10, ge=1, le=30)
    init_data_ttl: int = Field(default=86400, ge=60)
    jwt_ttl_minutes: int = Field(default=480, ge=5, le=10080)
    store_phone: str = ""
    store_telegram: str = ""
    store_address: str = ""

    @field_validator("app_env")
    @classmethod
    def _env(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("database_url")
    @classmethod
    def _db_url(cls, v: str) -> str:
        return normalize_database_url(v, BACKEND_DIR)

    @field_validator("upload_dir", "backup_dir")
    @classmethod
    def _dirs(cls, v: str) -> str:
        return anchor_path(v, BACKEND_DIR)

    def validate_for_runtime(self) -> None:
        """Приложение не стартует с небезопасной конфигурацией. Значения секретов в ошибки не попадают."""
        problems = (environment_problems(self.app_env, self.bot_token, self.debug, self.cors_origins)
                    + bot_token_problems(self.bot_token) + secret_key_problems(self.secret_key)
                    + admin_password_problems(self.admin_password, self.admin_username))
        if is_inside(self.backup_dir, self.upload_dir):
            problems.append("BACKUP_DIR не должен находиться внутри UPLOAD_DIR: эта папка раздаётся публично")
        db_file = sqlite_file_path(self.database_url)
        if db_file and is_inside(db_file, self.upload_dir):
            problems.append("Файл SQLite не должен находиться внутри UPLOAD_DIR: эта папка раздаётся публично")
        if problems:
            raise RuntimeError("Небезопасная конфигурация: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
