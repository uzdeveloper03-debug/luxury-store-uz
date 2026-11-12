import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.db import Base
import app.models  # noqa: F401


def test_migration_matches_models():
    """Миграция должна создавать ровно те таблицы и столбцы, что описаны в моделях."""
    url = f"sqlite:///{Path(tempfile.mkdtemp()) / 'm.db'}"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    migrated = set(insp.get_table_names()) - {"alembic_version"}
    assert migrated == set(Base.metadata.tables)
    for name, table in Base.metadata.tables.items():
        cols = {c["name"]: c["nullable"] for c in insp.get_columns(name)}
        assert cols == {c.name: c.nullable for c in table.columns}, name
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) <= {"alembic_version"}
