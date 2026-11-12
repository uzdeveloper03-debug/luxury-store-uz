"""Генератор ТЕСТОВЫХ Telegram WebApp initData (подписывается тестовым токеном).
Нужен, чтобы проверять backend без Telegram и без настоящего BOT_TOKEN.
Настоящий токен эта утилита принципиально не принимает.

Примеры:
  python scripts/make_test_init_data.py                    # данные для user 1001
  python scripts/make_test_init_data.py --user-id 7 --header
  python scripts/make_test_init_data.py --age-seconds 90000   # просроченные (должны отклоняться)
  python scripts/make_test_init_data.py --tamper              # подделанные (должны отклоняться)
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import DEFAULT_ENV, TEST_MARKER, parse_env_file  # noqa: E402


def ensure_test_token(token: str) -> None:
    if not token or TEST_MARKER not in token:
        raise ValueError(f"Допускаются только тестовые токены (содержат {TEST_MARKER}). "
                         "Настоящий токен бота сюда вводить нельзя.")


def build_init_data(token: str, user_id: int = 1001, first_name: str = "Test", username: str | None = None,
                    language_code: str = "ru", age_seconds: int = 0, tamper: bool = False,
                    ensure_ascii: bool = True) -> str:
    """Собирает initData по алгоритму из документации Telegram и подписывает тестовым токеном.
    age_seconds > 0 — данные «старше» на столько секунд; < 0 — дата в будущем."""
    ensure_test_token(token)
    user = {"id": user_id, "first_name": first_name, "language_code": language_code}
    if username:
        user["username"] = username
    fields = {"auth_date": str(int(time.time()) - age_seconds), "query_id": "AAH_TEST_ONLY",
              "user": json.dumps(user, ensure_ascii=ensure_ascii, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:  # меняем пользователя ПОСЛЕ подписи
        fields["user"] = json.dumps({**user, "id": user_id + 1}, ensure_ascii=ensure_ascii, separators=(",", ":"))
    return urlencode(fields)


def resolve_token(cli_token: str | None, env_file) -> str:
    if cli_token:
        return cli_token
    if os.environ.get("BOT_TOKEN"):
        return os.environ["BOT_TOKEN"]
    if os.path.exists(env_file):
        return parse_env_file(env_file).get("BOT_TOKEN", "")
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--user-id", type=int, default=1001)
    p.add_argument("--first-name", default="Test")
    p.add_argument("--username")
    p.add_argument("--lang", default="ru")
    p.add_argument("--age-seconds", type=int, default=0)
    p.add_argument("--tamper", action="store_true")
    p.add_argument("--token", help="тестовый токен (по умолчанию из BOT_TOKEN или .env.test)")
    p.add_argument("--env-file", default=str(DEFAULT_ENV))
    p.add_argument("--header", action="store_true", help="вывести готовый заголовок Authorization")
    a = p.parse_args()
    try:
        data = build_init_data(resolve_token(a.token, a.env_file), a.user_id, a.first_name, a.username,
                               a.lang, a.age_seconds, a.tamper)
    except ValueError as e:
        print(f"Ошибка: {e}\nСоздайте тестовое окружение: python scripts/gen_test_env.py", file=sys.stderr)
        return 2
    print(f"Authorization: tma {data}" if a.header else data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
