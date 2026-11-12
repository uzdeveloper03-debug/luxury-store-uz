import time

import pytest

from app.core.security import InvalidInitData, verify_init_data
from tests.conftest import BOT_TOKEN, make_init_data


def test_valid_init_data():
    user = verify_init_data(make_init_data(42), BOT_TOKEN, 86400)
    assert user["id"] == 42


def test_tampered_data_rejected():
    bad = make_init_data(42).replace("Test", "Hack")
    with pytest.raises(InvalidInitData):
        verify_init_data(bad, BOT_TOKEN, 86400)


def test_wrong_token_rejected():
    with pytest.raises(InvalidInitData):
        verify_init_data(make_init_data(42, bot_token="999:OTHER"), BOT_TOKEN, 86400)


def test_expired_rejected():
    old = make_init_data(42, auth_date=int(time.time()) - 90000)
    with pytest.raises(InvalidInitData):
        verify_init_data(old, BOT_TOKEN, 86400)


def test_missing_hash_and_empty_inputs_rejected():
    for bad in ("", "auth_date=1&user=%7B%7D", "garbage"):
        with pytest.raises(InvalidInitData):
            verify_init_data(bad, BOT_TOKEN, 86400)


def test_empty_bot_token_never_accepts():
    with pytest.raises(InvalidInitData):
        verify_init_data(make_init_data(42, bot_token=""), "", 86400)


def test_api_rejects_missing_and_fake_auth(client):
    assert client.get("/api/orders/my").status_code == 401
    assert client.get("/api/orders/my", headers={"Authorization": "tma fake"}).status_code == 401
    assert client.get("/api/orders/my", headers={"X-User-Id": "1"}).status_code == 401
