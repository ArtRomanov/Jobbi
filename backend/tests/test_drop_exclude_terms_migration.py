"""Migration 9e2b4d6f8a10: `vacancy_search_settings.exclude_terms` is dropped (backlog #12).

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
_REVISION = "9e2b4d6f8a10"
_PREVIOUS = "d7a1e3b9f2c4"


def _alembic(db_file: Path, *args: str) -> None:
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db_file}"}
    subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), *args],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


def _columns(engine: sa.Engine) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(engine).get_columns("vacancy_search_settings")
    }


def _settings(engine: sa.Engine) -> tuple[str, str | None]:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT user_id, description FROM vacancy_search_settings")
        ).one()
    return row.user_id, row.description


def test_upgrade_drops_exclude_terms_and_keeps_the_rest(tmp_path: Path) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO vacancy_search_settings "
                    "(user_id, description, exclude_terms) "
                    "VALUES ('u1', 'Senior React', '[\"java\"]')"
                )
            )

        _alembic(db_file, "upgrade", _REVISION)

        assert "exclude_terms" not in _columns(engine)
        assert _settings(engine) == ("u1", "Senior React")

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert "exclude_terms" in _columns(engine)
        assert _settings(engine) == ("u1", "Senior React")
        with engine.connect() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT exclude_terms FROM vacancy_search_settings")
                ).scalar_one()
                == "[]"
            )
    finally:
        engine.dispose()
