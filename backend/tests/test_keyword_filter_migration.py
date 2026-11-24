"""Migration b5d8f1a3c7e9: the pre-AI keyword filter columns.

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
_REVISION = "b5d8f1a3c7e9"
_PREVIOUS = "9e2b4d6f8a10"


def _alembic(db_file: Path, *args: str) -> None:
    env = os.environ | {"DATABASE_URL": f"sqlite+aiosqlite:///{db_file}"}
    subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), *args],
        cwd=_BACKEND,
        env=env,
        check=True,
        capture_output=True,
    )


def _columns(engine: sa.Engine, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(engine).get_columns(table)}


def test_upgrade_adds_filter_columns_with_defaults_and_downgrade_drops_them(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO vacancy_search_settings (user_id, description) "
                    "VALUES ('u1', 'Senior React')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO vacancy_seen_keys (id, user_id, external_key) "
                    "VALUES ('k1', 'u1', 'tg:chan/1')"
                )
            )

        _alembic(db_file, "upgrade", _REVISION)

        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT description, keywords, keyword_filter_enabled "
                    "FROM vacancy_search_settings"
                )
            ).one()
            assert row.description == "Senior React"
            assert row.keywords == "[]"
            assert row.keyword_filter_enabled in (True, 1)
            assert (
                conn.execute(
                    sa.text("SELECT filtered_at FROM vacancy_seen_keys")
                ).scalar_one()
                is None
            )

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert {"keywords", "keyword_filter_enabled"}.isdisjoint(
            _columns(engine, "vacancy_search_settings")
        )
        assert "filtered_at" not in _columns(engine, "vacancy_seen_keys")
        with engine.connect() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT description FROM vacancy_search_settings")
                ).scalar_one()
                == "Senior React"
            )
    finally:
        engine.dispose()
