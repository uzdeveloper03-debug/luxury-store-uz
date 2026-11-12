import hashlib
import hmac
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt


class InvalidInitData(Exception):
    pass


def verify_init_data(init_data: str, bot_token: str, ttl: int) -> dict:
    """Проверка Telegram WebApp initData (HMAC-SHA256) по документации Telegram.
    Возвращает данные пользователя или бросает InvalidInitData."""
    if not bot_token:
        raise InvalidInitData("bot token not configured")
    if not init_data or len(init_data) > 8192:
        raise InvalidInitData("bad length")
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        raise InvalidInitData("malformed")
    received = data.pop("hash", None)
    if not received:
        raise InvalidInitData("no hash")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InvalidInitData("bad signature")
    try:
        auth_date = int(data["auth_date"])
    except (KeyError, ValueError):
        raise InvalidInitData("bad auth_date")
    now = int(time.time())
    if now - auth_date > ttl or auth_date - now > 60:
        raise InvalidInitData("expired")
    try:
        user = json.loads(data["user"])
        if int(user["id"]) <= 0:
            raise ValueError("bad id")
    except (KeyError, ValueError, TypeError):
        raise InvalidInitData("no user")
    return user


def check_admin_credentials(username: str, password: str, exp_user: str, exp_pass: str) -> bool:
    ok_u = hmac.compare_digest(username.encode(), exp_user.encode())
    ok_p = hmac.compare_digest(password.encode(), exp_pass.encode())
    return bool(exp_pass) and ok_u and ok_p


def create_admin_token(secret: str, username: str, ttl_minutes: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    return jwt.encode({"sub": username, "role": "admin", "exp": exp}, secret, algorithm="HS256")


def decode_admin_token(secret: str, token: str) -> str:
    payload = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    if payload.get("role") != "admin":
        raise jwt.InvalidTokenError("not admin")
    return payload["sub"]


class LoginLimiter:
    """Блокировка перебора пароля: max_attempts неудач за window секунд с одного IP.
    Хранится в памяти процесса (при нескольких воркерах лимит считается на каждый)."""

    def __init__(self, max_attempts: int = 5, window: int = 900, global_max: int = 50):
        # global_max — общий потолок неудач со всех IP: защита от перебора с множества адресов
        self.max_attempts, self.window, self.global_max = max_attempts, window, global_max
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str) -> list[float]:
        now = time.time()
        fails = [t for t in self._fails.get(key, []) if now - t < self.window]
        self._fails[key] = fails
        return fails

    def blocked(self, key: str) -> bool:
        with self._lock:
            if len(self._prune(key)) >= self.max_attempts:
                return True
            total = 0
            for k in list(self._fails):
                n = len(self._prune(k))
                if n == 0:
                    del self._fails[k]  # не накапливаем пустые записи
                total += n
            return total >= self.global_max

    def fail(self, key: str) -> None:
        with self._lock:
            self._prune(key).append(time.time())

    def success(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._fails.clear()


login_limiter = LoginLimiter()
