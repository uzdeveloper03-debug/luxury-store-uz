"""Чистые тесты: только стандартная библиотека и PyJWT, без FastAPI/SQLAlchemy."""
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import pytest

from app.core.security import (InvalidInitData, LoginLimiter, check_admin_credentials,
                               create_admin_token, decode_admin_token, verify_init_data)
from app.core.validation import (admin_password_problems, anchor_path, bot_token_problems,
                                 is_inside, normalize_database_url, secret_key_problems,
                                 sqlite_file_path)

GOOD_TOKEN = "123456789:AAH_abcdefghijklmnopqrstuvwxyz012345"  # вымышленный, формат как у @BotFather


def test_secret_key_rules():
    assert secret_key_problems(secrets.token_urlsafe(48)) == []
    assert secret_key_problems("short")
    assert secret_key_problems("s" * 48)                      # 48 символов, но все одинаковые
    assert secret_key_problems("# " + "abcdefghij" * 4)       # комментарий вместо значения
    assert secret_key_problems("вставьте_сгенерированную_строку_случайных_символов")


def test_admin_password_rules():
    assert admin_password_problems("correct-horse-battery", "admin") == []
    assert admin_password_problems("short")
    assert admin_password_problems("aaaaaaaaaaaa")
    assert admin_password_problems("password123")
    assert admin_password_problems("# придумайте пароль")
    assert admin_password_problems("MyLoginName1", "myloginname1")  # совпадает с логином
    assert admin_password_problems("")


def test_bot_token_rules():
    assert bot_token_problems(GOOD_TOKEN) == []
    assert bot_token_problems("")
    assert bot_token_problems("# токен от BotFather")
    assert bot_token_problems("123456:TEST-TOKEN")


def test_database_url_normalization(tmp_path):
    base = tmp_path
    assert normalize_database_url("sqlite:///./luxury.db", base) == f"sqlite:///{base.as_posix()}/luxury.db"
    assert normalize_database_url("sqlite:///data/x.db?mode=rwc", base) == f"sqlite:///{base.as_posix()}/data/x.db?mode=rwc"
    assert normalize_database_url("sqlite://", base) == "sqlite://"
    assert normalize_database_url("sqlite:///:memory:", base) == "sqlite:///:memory:"
    assert normalize_database_url("sqlite:////var/lib/x.db", base) == "sqlite:////var/lib/x.db"
    assert normalize_database_url("sqlite:///C:/shop/x.db", base) == "sqlite:///C:/shop/x.db"
    assert normalize_database_url("postgresql://u:p@h/db", base) == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgres://u:p@h/db", base) == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("postgresql+psycopg://u:p@h/db", base) == "postgresql+psycopg://u:p@h/db"
    assert sqlite_file_path("sqlite:///./a.db") == "./a.db"
    assert sqlite_file_path("sqlite://") is None and sqlite_file_path("postgresql+psycopg://x/y") is None


def test_paths(tmp_path):
    assert anchor_path("./uploads", tmp_path).endswith("uploads") and is_inside(anchor_path("./uploads", tmp_path), tmp_path)
    assert anchor_path(str(tmp_path / "abs"), "/other") == str(tmp_path / "abs")
    assert is_inside(tmp_path / "up" / "bk", tmp_path / "up")
    assert is_inside(tmp_path / "up", tmp_path / "up")
    assert not is_inside(tmp_path / "bk", tmp_path / "up")
    assert not is_inside(tmp_path / "upload2", tmp_path / "up")  # похожий префикс — не вложенность
    assert not is_inside(tmp_path / "up" / ".." / "bk", tmp_path / "up")  # обход через ..


def test_jwt_roundtrip_and_rejections():
    key = secrets.token_urlsafe(48)
    assert decode_admin_token(key, create_admin_token(key, "admin", 5)) == "admin"
    with pytest.raises(jwt.PyJWTError):
        decode_admin_token("other-" + key, create_admin_token(key, "admin", 5))   # чужой ключ
    with pytest.raises(jwt.PyJWTError):
        decode_admin_token(key, create_admin_token(key, "admin", -1))             # истёк
    no_exp = jwt.encode({"sub": "admin", "role": "admin"}, key, algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_admin_token(key, no_exp)                                           # бессрочный токен
    not_admin = jwt.encode({"sub": "u", "role": "user", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
                           key, algorithm="HS256")
    with pytest.raises(jwt.PyJWTError):
        decode_admin_token(key, not_admin)                                        # не админ
    none_alg = jwt.encode({"sub": "admin", "role": "admin"}, None, algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        decode_admin_token(key, none_alg)                                         # alg=none


def test_admin_credentials_constant_time_api():
    assert check_admin_credentials("a", "secret-pass-1", "a", "secret-pass-1")
    assert not check_admin_credentials("a", "wrong", "a", "secret-pass-1")
    assert not check_admin_credentials("b", "secret-pass-1", "a", "secret-pass-1")
    assert not check_admin_credentials("", "", "", "")  # пустой пароль в конфиге никого не пускает


def test_limiter_per_ip_and_global_cap():
    lim = LoginLimiter(max_attempts=3, window=900, global_max=5)
    for _ in range(3):
        lim.fail("1.1.1.1")
    assert lim.blocked("1.1.1.1") and not lim.blocked("2.2.2.2")
    lim.fail("2.2.2.2"); lim.fail("3.3.3.3")
    assert lim.blocked("9.9.9.9")  # общий потолок: 5 неудач суммарно
    lim.reset()
    assert not lim.blocked("1.1.1.1")


def _init_data(uid, token=GOOD_TOKEN):
    f = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": "T"})}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(f.items()))
    sec = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    f["hash"] = hmac.new(sec, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(f)


def test_init_data_nonpositive_id_rejected():
    assert verify_init_data(_init_data(5), GOOD_TOKEN, 3600)["id"] == 5
    for bad in (0, -7):
        with pytest.raises(InvalidInitData):
            verify_init_data(_init_data(bad), GOOD_TOKEN, 3600)
