"""Migration a7c9e1b3d5f2: `forwarded_posts` (spec 012, 2.5).

Runs the real Alembic CLI against a temporary SQLite file (the local
`backend/alembic/` folder shadows the package inside pytest, so it cannot be
imported here).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
_REVISION = "a7c9e1b3d5f2"
_PREVIOUS = "f1a3d5c7e9b2"


def _alembic(db_file: Path, *args: str) -> None:
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db_file}"}
    subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), *args],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


_INSERT = sa.text(
    "INSERT INTO forwarded_posts (id, user_id, external_key, chat_id, message_id) "
    "VALUES (:id, 'u1', :key, :chat_id, 7)"
)


def test_upgrade_creates_forwarded_posts_and_downgrade_drops_it(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        assert "forwarded_posts" not in sa.inspect(engine).get_table_names()

        _alembic(db_file, "upgrade", _REVISION)

        inspector = sa.inspect(engine)
        columns = {c["name"]: c for c in inspector.get_columns("forwarded_posts")}
        assert set(columns) == {
            "id",
            "user_id",
            "external_key",
            "chat_id",
            "message_id",
            "created_at",
            "reported_at",
        }
        assert columns["reported_at"]["nullable"] is True
        assert columns["chat_id"]["nullable"] is False
        assert isinstance(columns["chat_id"]["type"], sa.BigInteger)
        assert isinstance(columns["message_id"]["type"], sa.BigInteger)
        [fk] = inspector.get_foreign_keys("forwarded_posts")
        assert (fk["referred_table"], fk["options"].get("ondelete")) == (
            "users",
            "CASCADE",
        )
        [unique] = inspector.get_unique_constraints("forwarded_posts")
        assert unique["column_names"] == ["user_id", "external_key"]

        # A private channel id does not fit 32 bits.
        with engine.begin() as conn:
            conn.execute(
                _INSERT, {"id": "f1", "key": "tgc:1/1", "chat_id": -1001234567890}
            )
            row = conn.execute(
                sa.text("SELECT chat_id, created_at, reported_at FROM forwarded_posts")
            ).one()
        assert row.chat_id == -1001234567890
        assert row.created_at is not None  # server default
        assert row.reported_at is None
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(_INSERT, {"id": "f2", "key": "tgc:1/1", "chat_id": 1})

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert "forwarded_posts" not in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()
