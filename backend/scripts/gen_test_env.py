"""Создаёт файл тестового окружения .env.test (НЕ .env) со случайными тестовыми секретами.
Файл не перезаписывается без --force; значения секретов на экран не выводятся.
Токен в нём вымышленный (метка TEST_ONLY): к Telegram с ним подключиться невозможно."""
import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import DEFAULT_ENV, TEST_MARKER  # noqa: E402


def build_env_text() -> str:
    fake_token = f"1000000000:{TEST_MARKER}_{secrets.token_hex(16)}"
    return "\n".join([
        "# Тестовое окружение Luxury Store UZ. Не содержит настоящих токенов. В git не попадает.",
        "APP_ENV=test",
        f"BOT_TOKEN={fake_token}",
        f"SECRET_KEY={secrets.token_urlsafe(48)}",
        "ADMIN_USERNAME=admin",
        f"ADMIN_PASSWORD={secrets.token_urlsafe(18)}",
        "DATABASE_URL=sqlite:///./test_local.db",
        "UPLOAD_DIR=./test_uploads",
        "BACKUP_DIR=./test_backups",
        "BACKUP_KEEP=5",
        "CORS_ORIGINS=http://localhost:5173,http://localhost:5174",
        "DEBUG=true",
        "",
    ])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(DEFAULT_ENV))
    p.add_argument("--force", action="store_true", help="перезаписать существующий тестовый файл")
    a = p.parse_args()
    out = Path(a.out)
    if out.name == ".env":
        print("Отказ: этот скрипт никогда не пишет в .env", file=sys.stderr)
        return 2
    if out.exists() and not a.force:
        print(f"Файл {out} уже существует, не перезаписываю (используйте --force).", file=sys.stderr)
        return 1
    out.write_text(build_env_text(), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    print(f"Создан {out}\nСекреты записаны только в файл. Дальше: python scripts/run_local.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
