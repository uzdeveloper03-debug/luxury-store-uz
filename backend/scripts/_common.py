"""Общее для dev-скриптов. Только стандартная библиотека."""
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
DEFAULT_ENV = ROOT / ".env.test"
TEST_MARKER = "TEST_ONLY"  # метка тестовых токенов; настоящий токен BotFather её не содержит


def parse_env_file(path) -> dict:
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out
