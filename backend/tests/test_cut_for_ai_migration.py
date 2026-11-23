"""Migration e4b7c2a91f03: `vacancy_seen_keys.cut_for_ai` (spec 012, 2.1).

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
_REVISION = "e4b7c2a91f03"
_PREVIOUS = "cd2779fea0d9"


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
        for column in sa.inspect(engine).get_columns("vacancy_seen_keys")
    }


def test_upgrade_adds_flag_false_for_existing_rows_and_downgrade_drops_it(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO vacancy_seen_keys (id, user_id, external_key) "
                    "VALUES ('k1', 'u1', 'tg:chan/1')"
                )
            )

        _alembic(db_file, "upgrade", _REVISION)

        column = _columns(engine)["cut_for_ai"]
        assert column["nullable"] is False
        with engine.connect() as conn:
            assert conn.execute(
                sa.text("SELECT cut_for_ai FROM vacancy_seen_keys")
            ).scalar_one() in (False, 0)

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert "cut_for_ai" not in _columns(engine)
        with engine.connect() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT external_key FROM vacancy_seen_keys")
                ).scalar_one()
                == "tg:chan/1"
            )
    finally:
        engine.dispose()
