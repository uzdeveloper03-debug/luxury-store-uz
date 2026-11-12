import sqlite3

from app.core.config import get_settings
from app.services import backup


def test_sqlite_backup_is_valid_and_rotated(tmp_path, monkeypatch):
    db = tmp_path / "shop.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.execute("INSERT INTO t VALUES (7)")
    con.commit()
    con.close()
    s = get_settings()
    monkeypatch.setattr(s, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(s, "backup_dir", str(tmp_path / "bk"))
    monkeypatch.setattr(s, "backup_keep", 2)
    paths = [backup.make_backup() for _ in range(4)]
    assert paths[-1].exists()
    assert sqlite3.connect(paths[-1]).execute("SELECT x FROM t").fetchone() == (7,)  # копия читается
    assert len(backup.list_backups()) == 2  # старые удалены


def test_backup_endpoint(client, admin, tmp_path, monkeypatch):
    db = tmp_path / "shop.db"
    sqlite3.connect(db).close()
    s = get_settings()
    monkeypatch.setattr(s, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(s, "backup_dir", str(tmp_path / "bk"))
    assert client.post("/api/admin/backups", headers=admin).status_code == 201
    assert len(client.get("/api/admin/backups", headers=admin).json()) == 1
