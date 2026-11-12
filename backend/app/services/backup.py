"""Резервное копирование БД.
SQLite — через встроенный backup API (безопасно при работающем приложении).
PostgreSQL — через pg_dump (должен быть установлен). Хранится BACKUP_KEEP последних копий.
Запуск вручную/по cron:  python -m app.services.backup
Копии лежат на том же сервере — периодически копируйте их в другое место!"""
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.validation import is_inside

_SUFFIXES = (".sqlite3", ".dump")


class BackupError(Exception):
    pass


def _backup_files(d: Path) -> list[Path]:
    # сортировка по имени (в нём UTC-время с микросекундами), а не по mtime: надёжнее при копировании файлов
    return sorted((f for f in d.iterdir() if f.is_file() and f.name.startswith("luxury-")
                   and f.suffix in _SUFFIXES), key=lambda f: f.name, reverse=True)


def list_backups() -> list[dict]:
    d = Path(get_settings().backup_dir)
    if not d.exists():
        return []
    return [{"name": f.name, "size": f.stat().st_size} for f in _backup_files(d)]


def make_backup() -> Path:
    s = get_settings()
    url = make_url(s.database_url)
    out_dir = Path(s.backup_dir)
    if is_inside(out_dir, s.upload_dir):  # UPLOAD_DIR раздаётся публично — копии БД там недопустимы
        raise BackupError("BACKUP_DIR находится внутри UPLOAD_DIR: копия базы стала бы общедоступной")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(out_dir, 0o700)
    except OSError:
        pass  # на Windows права POSIX не применяются
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    if url.get_backend_name() == "sqlite":
        if not url.database or url.database == ":memory:":
            raise BackupError("In-memory SQLite не поддерживает резервное копирование")
        target = out_dir / f"luxury-{ts}.sqlite3"
        if not Path(url.database).is_file():  # connect() молча создал бы пустую БД и «успешно» скопировал её
            raise BackupError("Файл базы данных не найден")
        src = sqlite3.connect(url.database)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    elif url.get_backend_name() == "postgresql":
        target = out_dir / f"luxury-{ts}.dump"
        cmd = ["pg_dump", "--format=custom", "--no-owner", "--file", str(target),
               "-h", url.host or "localhost", "-p", str(url.port or 5432),
               "-U", url.username or "", url.database or ""]
        env = {**os.environ, "PGPASSWORD": url.password or ""}
        try:
            subprocess.run(cmd, env=env, check=True, capture_output=True, timeout=600)
        except FileNotFoundError:
            raise BackupError("pg_dump не найден: установите postgresql-client")
        except subprocess.CalledProcessError as e:
            target.unlink(missing_ok=True)
            raise BackupError(f"pg_dump завершился с ошибкой: {e.stderr.decode()[:300]}")
    else:
        raise BackupError("Неподдерживаемая СУБД")
    try:
        os.chmod(target, 0o600)  # копия содержит персональные данные покупателей
    except OSError:
        pass
    _rotate(out_dir, s.backup_keep)
    return target


def _rotate(d: Path, keep: int) -> None:
    for old in _backup_files(d)[max(keep, 1):]:
        old.unlink(missing_ok=True)


if __name__ == "__main__":
    print(make_backup())
