"""Проверка готовности к подключению настоящего Telegram-бота и хостинга.
Работает ОФЛАЙН: к Telegram и в сеть не обращается, значения секретов не печатает.

  python -m tools.check_readiness
"""
import os
import sys
from pathlib import Path

from app.core.validation import (admin_password_problems, bot_token_problems, is_inside, origin_of,
                                 secret_key_problems, sqlite_file_path, webapp_url_problems)
from tools.test_init_data import TEST_BOT_TOKEN

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def load_env() -> dict:
    env: dict = {}
    try:
        from dotenv import dotenv_values
        for f in (ROOT / ".env", BACKEND / ".env"):
            if f.is_file():
                env.update({k: v for k, v in dotenv_values(f, encoding="utf-8").items() if v is not None})
    except ImportError:
        pass
    env.update({k: v for k, v in os.environ.items() if k.isupper()})  # переменные окружения приоритетнее
    return env


def main() -> int:
    e = {k: (v or "").strip() for k, v in load_env().items()}
    rows, blockers = [], 0

    def add(name, status, note=""):
        nonlocal blockers
        rows.append((name, status, note))
        if status == "НЕТ":
            blockers += 1

    has_env = (ROOT / ".env").is_file() or (BACKEND / ".env").is_file()
    add(".env", "OK" if has_env else "НЕТ", "" if has_env else "создайте .env по образцу .env.example")

    tok = e.get("BOT_TOKEN", "")
    if tok == TEST_BOT_TOKEN or "TESTONLY" in tok:
        add("BOT_TOKEN", "ТЕСТОВЫЙ", "вымышленный токен: бот в Telegram не запустится")
    elif bot_token_problems(tok):
        add("BOT_TOKEN", "НЕТ", bot_token_problems(tok)[0])
    else:
        add("BOT_TOKEN", "ПРОВЕРИТЬ", "формат верный; действительность токена офлайн проверить нельзя")

    for name, probs in (("SECRET_KEY", secret_key_problems(e.get("SECRET_KEY", ""))),
                        ("ADMIN_PASSWORD", admin_password_problems(e.get("ADMIN_PASSWORD", ""), e.get("ADMIN_USERNAME", "admin")))):
        add(name, "НЕТ" if probs else "OK", probs[0] if probs else "")

    wp = webapp_url_problems(e.get("WEBAPP_URL", ""))
    add("WEBAPP_URL", "НЕТ" if wp else "ПРОВЕРИТЬ", wp[0] if wp else "формат верный; доступность домена офлайн проверить нельзя")

    ids = [x.strip() for x in e.get("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip()]
    bad_ids = [x for x in ids if not x.isdigit()]
    add("ADMIN_TELEGRAM_IDS", "OK" if ids and not bad_ids else "НЕТ",
        "" if ids and not bad_ids else "укажите числовые Telegram id через запятую")

    mini = origin_of(e.get("WEBAPP_URL", ""))
    add("CORS для Mini App", "OK" if mini else "НЕТ", "origin Mini App добавляется автоматически из WEBAPP_URL" if mini else "зависит от WEBAPP_URL")

    db = e.get("DATABASE_URL", "sqlite:///./luxury.db")
    add("БД", "OK", "SQLite (для боевого режима рекомендуется PostgreSQL)" if db.startswith("sqlite") else "PostgreSQL")
    up, bk = e.get("UPLOAD_DIR", "./uploads"), e.get("BACKUP_DIR", "./backups")
    ok_dirs = not is_inside(BACKEND / bk, BACKEND / up) and not (sqlite_file_path(db) and is_inside(BACKEND / sqlite_file_path(db), BACKEND / up))
    add("Папки uploads/backups", "OK" if ok_dirs else "НЕТ", "" if ok_dirs else "БД/копии не должны лежать в публичной папке uploads")

    print(f"{'Параметр':<24}{'Статус':<11}Комментарий")
    for n, s, note in rows:
        print(f"{n:<24}{s:<11}{note}")
    print("\nТребует НАСТОЯЩЕГО токена от @BotFather: запуск бота, отправка сообщений, проверка настоящей подписи initData.")
    print("Требует внешнего хостинга: публичный HTTPS-домен для Mini App и API, работа 24/7, webhook, резервные копии вне сервера.")
    print(f"\nБлокирующих проблем: {blockers}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
