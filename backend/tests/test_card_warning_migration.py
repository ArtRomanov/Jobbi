"""Migration c3e5a7b9d1f2: `chat_change_cards.warning` (backlog #27).

Runs the real Alembic CLI against a temporary SQLite file (the local
`backend/alembic/` folder shadows the package inside pytest, so it cannot be
imported here).
"""

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
_REVISION = "c3e5a7b9d1f2"
_PREVIOUS = "b5d8f1a3c7e9"


def _alembic(db_file: Path, *args: str) -> None:
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db_file}"}
    subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), *args],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


def _columns(engine: sa.Engine) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in sa.inspect(engine).get_columns("chat_change_cards")
    }


def _card_ops(engine: sa.Engine) -> list[str]:
    with engine.connect() as conn:
        return list(conn.execute(sa.text("SELECT op FROM chat_change_cards")).scalars())


def test_upgrade_adds_nullable_warning_and_downgrade_drops_it(tmp_path: Path) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO chat_change_cards "
                    "(id, application_id, message_id, cv_id, op, before_text, "
                    "after_text, state, created_at) VALUES "
                    "('c1', 'a1', 'm1', 'cv1', 'remove', 'x', '', 'pending', "
                    "'2026-11-25 12:00:00')"
                )
            )
        assert "warning" not in _columns(engine)

        _alembic(db_file, "upgrade", _REVISION)

        columns = _columns(engine)
        assert columns["warning"]["nullable"] is True
        assert isinstance(columns["warning"]["type"], sa.Text)
        with engine.connect() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT warning FROM chat_change_cards")
                ).scalar_one()
                is None
            )

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert "warning" not in _columns(engine)
        assert _card_ops(engine) == ["remove"]
    finally:
        engine.dispose()
