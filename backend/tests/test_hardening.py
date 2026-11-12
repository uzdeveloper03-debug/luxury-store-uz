"""API-тесты усиления безопасности (нужны FastAPI/SQLAlchemy — запускаются через pytest)."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models import Order, ProductSize
from app.services import backup
from app.services.orders import InvalidTransition, change_status
from tests.conftest import order_payload, tma


def test_search_wildcards_are_literal(client, seed, admin):
    assert client.get("/api/products?q=%25").json()["total"] == 0   # '%' ищется как символ, а не «любой текст»
    assert client.get("/api/products?q=_").json()["total"] == 0
    assert client.get("/api/admin/products?q=%25", headers=admin).json() == []
    assert client.get("/api/products?q=AIR").json()["total"] == 1   # регистр не важен


def test_active_order_limit_per_user(client, seed, admin):
    client.put(f"/api/admin/sizes/{seed['s41']}", json={"stock": 50}, headers=admin)
    item = [{"size_id": seed["s41"], "quantity": 1}]
    for _ in range(5):
        assert client.post("/api/orders", json=order_payload(item), headers=tma(1)).status_code == 201
    assert client.post("/api/orders", json=order_payload(item), headers=tma(1)).status_code == 429
    assert client.post("/api/orders", json=order_payload(item), headers=tma(2)).status_code == 201  # другим не мешает


def test_security_headers(client, admin):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/admin/orders", headers=admin).headers["cache-control"] == "no-store"


def test_backup_guards(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", f"sqlite:///{tmp_path / 'missing.db'}")
    monkeypatch.setattr(s, "backup_dir", str(tmp_path / "bk"))
    with pytest.raises(backup.BackupError):          # нет файла базы — не создаём «пустую» копию
        backup.make_backup()
    real = tmp_path / "real.db"
    real.write_bytes(b"")
    monkeypatch.setattr(s, "database_url", f"sqlite:///{real}")
    monkeypatch.setattr(s, "backup_dir", str(s.upload_dir) + "/bk")
    with pytest.raises(backup.BackupError):          # копии внутри публичной папки запрещены
        backup.make_backup()


def test_stale_status_change_cannot_double_release(client, seed, admin, Session):
    a = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 2}]), headers=tma(1)).json()
    client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 1}]), headers=tma(2))
    db = Session()
    stale = db.scalar(select(Order).where(Order.id == a["id"]).options(selectinload(Order.items)))
    r = client.patch(f"/api/admin/orders/{a['id']}/status", json={"status": "cancelled"}, headers=admin)
    assert r.status_code == 200
    with pytest.raises(InvalidTransition):           # «устаревший» объект пытается отменить заказ повторно
        change_status(db, stale, "cancelled")
    size = db.scalar(select(ProductSize).where(ProductSize.id == seed["s41"]))
    assert size.reserved == 1                         # резерв второго заказа не пострадал
    db.close()
