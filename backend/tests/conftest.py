import hashlib
import hmac
import json
import os
import tempfile
import time
from urllib.parse import urlencode

_tmp = tempfile.mkdtemp()
os.environ.update(
    BOT_TOKEN="123456:TEST-TOKEN", SECRET_KEY="s" * 48, ADMIN_USERNAME="admin",
    ADMIN_PASSWORD="correct-horse-battery", DATABASE_URL="sqlite://",
    UPLOAD_DIR=os.path.join(_tmp, "uploads"), BACKUP_DIR=os.path.join(_tmp, "backups"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.db import Base, get_db  # noqa: E402
from app.core.security import login_limiter  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Brand, Category, Product, ProductSize  # noqa: E402

BOT_TOKEN = os.environ["BOT_TOKEN"]


def make_init_data(user_id=1001, bot_token=BOT_TOKEN, auth_date=None, first_name="Test"):
    """Независимая реализация алгоритма из документации Telegram (для тестов)."""
    fields = {"auth_date": str(auth_date if auth_date is not None else int(time.time())),
              "query_id": "AAH123",
              "user": json.dumps({"id": user_id, "first_name": first_name, "language_code": "ru"})}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def tma(user_id=1001, **kw):
    return {"Authorization": "tma " + make_init_data(user_id, **kw)}


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(Session):
    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _get_db
    login_limiter.reset()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def admin(client):
    r = client.post("/api/admin/login", json={"username": "admin", "password": "correct-horse-battery"})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def seed(Session):
    """Бренд, категория и два товара: опубликованный (размеры 41:3, 42:1) и скрытый."""
    db = Session()
    b, c = Brand(name="Nike"), Category(slug="run", name_ru="Бег", name_uz="Yugurish")
    db.add_all([b, c])
    db.commit()
    p = Product(name="Air Max", brand_id=b.id, category_id=c.id, price=1_500_000,
                purchase_price=900_000, is_published=True)
    hidden = Product(name="Secret", brand_id=b.id, category_id=c.id, price=2_000_000, is_published=False)
    db.add_all([p, hidden])
    db.commit()
    s41 = ProductSize(product_id=p.id, size="41", stock=3, reserved=0)
    s42 = ProductSize(product_id=p.id, size="42", stock=1, reserved=0)
    sh = ProductSize(product_id=hidden.id, size="40", stock=5, reserved=0)
    db.add_all([s41, s42, sh])
    db.commit()
    out = dict(brand=b.id, category=c.id, product=p.id, hidden=hidden.id,
               s41=s41.id, s42=s42.id, shidden=sh.id)
    db.close()
    return out


def order_payload(items, **over):
    d = {"customer_name": "Али Валиев", "phone": "+998 90 123-45-67",
         "address": "Ташкент, ул. Навои 1", "items": items}
    d.update(over)
    return d
