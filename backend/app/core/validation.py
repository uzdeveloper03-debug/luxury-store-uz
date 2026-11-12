"""Проверки конфигурации. Только стандартная библиотека — модуль тестируется без FastAPI.
Функции никогда не включают значения секретов в тексты ошибок."""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

BOT_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")
_PLACEHOLDERS = ("changeme", "change_me", "change-me", "your_secret", "your_password", "your-secret",
                 "example", "вставьте", "придумайте", "сгенерир", "todo", "xxxx")
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop", "qwerty12345",
    "admin12345", "administrator", "adminadmin", "luxurystore", "luxury12345", "letmein123", "iloveyou123",
}
_SQLITE_RE = re.compile(r"^(sqlite(?:\+[a-z0-9]+)?):///(?!/)(.*)$", re.I)
_WIN_ABS = re.compile(r"^[A-Za-z]:[\\/]")


def _placeholder(v: str) -> bool:
    low = v.strip().lower()
    return low.startswith("#") or any(p in low for p in _PLACEHOLDERS)


def secret_key_problems(v: str) -> list[str]:
    out = []
    if len(v) < 32:
        out.append("SECRET_KEY должен быть длиной не менее 32 символов")
    elif _placeholder(v):
        out.append("SECRET_KEY похож на шаблон или комментарий — сгенерируйте случайное значение")
    elif len(set(v)) < 12:
        out.append("SECRET_KEY слишком предсказуем (мало различных символов)")
    return out


def admin_password_problems(pw: str, username: str = "") -> list[str]:
    out = []
    if len(pw) < 10:
        out.append("ADMIN_PASSWORD должен быть длиной не менее 10 символов")
    elif _placeholder(pw):
        out.append("ADMIN_PASSWORD похож на шаблон или комментарий — задайте свой пароль")
    elif pw.lower() in _COMMON_PASSWORDS or (username and pw.lower() == username.lower()):
        out.append("ADMIN_PASSWORD слишком распространённый или совпадает с логином")
    elif len(set(pw)) < 6:
        out.append("ADMIN_PASSWORD слишком простой (мало различных символов)")
    return out


def bot_token_problems(v: str) -> list[str]:
    if not v:
        return ["BOT_TOKEN не задан"]
    if not BOT_TOKEN_RE.match(v):
        return ["BOT_TOKEN не похож на токен @BotFather (формат 123456789:AA...)"]
    return []


TEST_TOKEN_MARKER = "TEST_ONLY"  # у всех тестовых токенов этого проекта; настоящий токен BotFather его не содержит
APP_ENVS = ("development", "test", "production")


def is_test_bot_token(v: str) -> bool:
    return TEST_TOKEN_MARKER in v


def environment_problems(app_env: str, bot_token: str, debug: bool, cors_origins: str) -> list[str]:
    """Защита от смешивания тестового и боевого режимов."""
    if app_env not in APP_ENVS:
        return [f"APP_ENV должен быть одним из: {', '.join(APP_ENVS)}"]
    out = []
    if app_env == "test" and bot_token and not is_test_bot_token(bot_token):
        out.append("В режиме APP_ENV=test разрешён только тестовый BOT_TOKEN (с меткой TEST_ONLY)")
    if app_env == "production":
        if is_test_bot_token(bot_token):
            out.append("В production нельзя использовать тестовый BOT_TOKEN")
        if debug:
            out.append("В production DEBUG должен быть false")
        origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
        if any(o == "*" or not o.startswith("https://") for o in origins):
            out.append("В production CORS_ORIGINS должны быть https-адресами, без '*'")
    return out


def _is_abs(p: str) -> bool:
    return Path(p).is_absolute() or bool(_WIN_ABS.match(p))


def anchor_path(value: str, base_dir) -> str:
    """Относительный путь считается от папки backend/, а не от текущей директории запуска."""
    if _is_abs(value):
        return value
    return os.path.normpath(str(Path(base_dir) / value))


def normalize_database_url(url: str, base_dir) -> str:
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):  # без явного драйвера SQLAlchemy ищет psycopg2, которого нет
            return "postgresql+psycopg://" + url[len(prefix):]
    m = _SQLITE_RE.match(url)
    if m:
        path, sep, query = m.group(2).partition("?")
        if path and not path.startswith(":memory:") and not _is_abs(path):
            path = (Path(base_dir) / path).as_posix()
            return f"{m.group(1)}:///{path}{sep}{query}"
    return url


def sqlite_file_path(url: str) -> str | None:
    m = _SQLITE_RE.match(url)
    if not m:
        return None
    path = m.group(2).partition("?")[0]
    return None if not path or path.startswith(":memory:") else path


def is_inside(child, parent) -> bool:
    c, p = Path(child).resolve(), Path(parent).resolve()
    return c == p or p in c.parents


def origin_of(url: str) -> str:
    p = urlsplit(url.strip())
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


def webapp_url_problems(url: str) -> list[str]:
    if not url:
        return ["WEBAPP_URL не задан"]
    p = urlsplit(url.strip())
    out = []
    if p.scheme != "https":
        out.append("WEBAPP_URL должен начинаться с https:// (Telegram открывает Mini App только по HTTPS)")
    host = (p.hostname or "").lower()
    if not host or host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local") or "." not in host:
        out.append("WEBAPP_URL должен указывать на публичный домен, а не на localhost")
    return out
