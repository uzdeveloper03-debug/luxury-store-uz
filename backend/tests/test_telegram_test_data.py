"""Проверка Telegram WebApp initData на специально созданных ТЕСТОВЫХ данных.
Чистые тесты: без сети, без Telegram, без настоящего BOT_TOKEN."""
import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.security import InvalidInitData, verify_init_data
from app.core.validation import (bot_token_problems, environment_problems, is_test_bot_token,
                                 secret_key_problems, admin_password_problems)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gen = _load("make_test_init_data")
genenv = _load("gen_test_env")
TOKEN = "1000000000:TEST_ONLY_0123456789abcdef0123456789abcdef"
OTHER = "1000000000:TEST_ONLY_ffffffffffffffffffffffffffffffff"
TTL = 86400


def test_generated_data_is_accepted_and_roundtrips_user():
    u = verify_init_data(gen.build_init_data(TOKEN, user_id=77, first_name="Ali", username="ali_u", language_code="uz"), TOKEN, TTL)
    assert (u["id"], u["first_name"], u["username"], u["language_code"]) == (77, "Ali", "ali_u", "uz")


def test_unicode_and_special_characters_in_names():
    for name in ("Алишер Валиев", "O‘ktam", "A&B = C+D %20 #1", "Имя 🙂"):
        for ascii_json in (True, False):  # Telegram может отдавать JSON и так, и так — подпись считается по строке
            d = gen.build_init_data(TOKEN, first_name=name, ensure_ascii=ascii_json)
            assert verify_init_data(d, TOKEN, TTL)["first_name"] == name


def test_tampered_expired_future_and_foreign_signatures_rejected():
    cases = {
        "подделанный user": gen.build_init_data(TOKEN, tamper=True),
        "просрочен": gen.build_init_data(TOKEN, age_seconds=TTL + 60),
        "дата в будущем": gen.build_init_data(TOKEN, age_seconds=-3600),
        "подписан другим токеном": gen.build_init_data(OTHER),
    }
    for label, data in cases.items():
        with pytest.raises(InvalidInitData):
            verify_init_data(data, TOKEN, TTL)


def test_boundary_of_ttl():
    verify_init_data(gen.build_init_data(TOKEN, age_seconds=TTL - 30), TOKEN, TTL)  # ещё действует
    with pytest.raises(InvalidInitData):
        verify_init_data(gen.build_init_data(TOKEN, age_seconds=TTL + 30), TOKEN, TTL)


def test_swapping_or_dropping_fields_is_detected():
    good = gen.build_init_data(TOKEN, user_id=5)
    with pytest.raises(InvalidInitData):
        verify_init_data(good.replace("query_id=", "x_id="), TOKEN, TTL)        # переименованное поле
    with pytest.raises(InvalidInitData):
        verify_init_data(good + "&extra=1", TOKEN, TTL)                          # добавленное поле
    with pytest.raises(InvalidInitData):
        verify_init_data("&".join(p for p in good.split("&") if not p.startswith("hash=")), TOKEN, TTL)


def test_generator_refuses_real_looking_token():
    real_like = "123456789:AAH" + "x" * 32
    with pytest.raises(ValueError):
        gen.build_init_data(real_like)
    assert not is_test_bot_token(real_like) and is_test_bot_token(TOKEN)


def test_generated_test_env_is_valid_and_safe():
    env = {}
    for line in genenv.build_env_text().splitlines():
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            env[k] = v
    assert env["APP_ENV"] == "test" and is_test_bot_token(env["BOT_TOKEN"])
    assert bot_token_problems(env["BOT_TOKEN"]) == []
    assert secret_key_problems(env["SECRET_KEY"]) == []
    assert admin_password_problems(env["ADMIN_PASSWORD"], env["ADMIN_USERNAME"]) == []
    assert environment_problems(env["APP_ENV"], env["BOT_TOKEN"], True, env["CORS_ORIGINS"]) == []
    assert genenv.build_env_text() != genenv.build_env_text()  # секреты случайные при каждом запуске


def test_gen_test_env_never_writes_dot_env_or_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gen", "--out", str(tmp_path / ".env")])
    assert genenv.main() == 2 and not (tmp_path / ".env").exists()
    target = tmp_path / ".env.test"
    monkeypatch.setattr(sys, "argv", ["gen", "--out", str(target)])
    assert genenv.main() == 0 and target.exists()
    before = target.read_text(encoding="utf-8")
    assert genenv.main() == 1 and target.read_text(encoding="utf-8") == before  # без --force не перезаписывает


def test_environment_guards():
    real_like = "123456789:AAH" + "x" * 32
    assert environment_problems("development", real_like, False, "") == []
    assert environment_problems("test", real_like, True, "")                          # test + настоящий токен — запрещено
    assert environment_problems("production", TOKEN, False, "https://shop.example")    # production + тестовый токен — запрещено
    assert environment_problems("production", real_like, True, "")                     # production + DEBUG — запрещено
    assert environment_problems("production", real_like, False, "*")
    assert environment_problems("production", real_like, False, "http://shop.example")
    assert environment_problems("production", real_like, False, "https://shop.example") == []
    assert environment_problems("staging", real_like, False, "")                       # неизвестный режим
