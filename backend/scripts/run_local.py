"""Локальный запуск backend на ТЕСТОВОМ окружении: миграции + uvicorn на 127.0.0.1.
Telegram не используется. Бот не запускается. Работает только при APP_ENV=test с тестовым токеном.
  python scripts/run_local.py [--env-file ../.env.test] [--port 8000]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import BACKEND, DEFAULT_ENV, TEST_MARKER, parse_env_file  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", default=str(DEFAULT_ENV))
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    if not os.path.exists(a.env_file):
        print(f"Нет файла {a.env_file}. Сначала: python scripts/gen_test_env.py", file=sys.stderr)
        return 2
    for k, v in parse_env_file(a.env_file).items():
        os.environ[k] = v  # переменные окружения приоритетнее любого .env — настоящий .env не повлияет
    if os.environ.get("APP_ENV") != "test" or TEST_MARKER not in os.environ.get("BOT_TOKEN", ""):
        print("Отказ: нужен APP_ENV=test и тестовый BOT_TOKEN (метка TEST_ONLY).", file=sys.stderr)
        return 2
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")
    print(f"Миграции применены. Сервер: http://127.0.0.1:{a.port}  (остановка: Ctrl+C)")
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=a.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
