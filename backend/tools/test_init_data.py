"""Генератор ТЕСТОВЫХ Telegram WebApp initData — для проверки backend без Telegram.

Данные подписываются токеном по алгоритму из документации Telegram. Используйте только вымышленный
тестовый токен (по умолчанию TEST_BOT_TOKEN). Реальный токен для этого не нужен.

  python -m tools.test_init_data --user-id 1001
"""
import argparse
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

TEST_BOT_TOKEN = "123456789:TESTONLY_not_a_real_token_0123456789"  # вымышленный, не работает в Telegram


def build_init_data(user_id: int = 1001, bot_token: str = TEST_BOT_TOKEN, auth_date: int | None = None,
                    first_name: str = "Test", language_code: str = "ru", extra: dict | None = None) -> str:
    user = {"id": user_id, "first_name": first_name, "language_code": language_code}
    fields = {"auth_date": str(auth_date if auth_date is not None else int(time.time())),
              "query_id": "AAH_TEST_QUERY", "user": json.dumps(user, ensure_ascii=False, separators=(",", ":"))}
    fields.update(extra or {})
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-id", type=int, default=1001)
    ap.add_argument("--name", default="Test")
    args = ap.parse_args()
    token = os.environ.get("BOT_TOKEN") or TEST_BOT_TOKEN
    if token != TEST_BOT_TOKEN:
        print("! BOT_TOKEN из окружения отличается от тестового. Для проверок используйте тестовый токен.\n")
    print("Authorization: tma " + build_init_data(args.user_id, token, first_name=args.name))


if __name__ == "__main__":
    main()
