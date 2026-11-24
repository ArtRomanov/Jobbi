"""Migration f1a3d5c7e9b2: `vacancies.links` (spec 012, 2.1).

Runs the real Alembic CLI against a temporary SQLite file (the local
`backend/alembic/` folder shadows the package inside pytest, so it cannot be
imported here).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
_REVISION = "f1a3d5c7e9b2"
_PREVIOUS = "e4b7c2a91f03"


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
        column["name"]: column for column in sa.inspect(engine).get_columns("vacancies")
    }


_INSERT = sa.text(
    "INSERT INTO vacancies (id, user_id, external_key, url, text, posted_at, "
    "found_at, state, eval_attempts, from_initial_scan, updated_at) VALUES "
    "(:id, 'u1', :key, 'https://t.me/chan/1', 'text', '2026-11-23 10:00:00', "
    "'2026-11-23 10:00:00', 'pending', 0, 0, '2026-11-23 10:00:00')"
)


def test_upgrade_adds_nullable_links_and_downgrade_drops_them(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        with engine.begin() as conn:
            conn.execute(_INSERT, {"id": "v1", "key": "tg:chan/1"})

        _alembic(db_file, "upgrade", _REVISION)

        assert _columns(engine)["links"]["nullable"] is True
        links = [[2, "https://jobs.example.com/a"]]
        with engine.begin() as conn:
            assert (
                conn.execute(
                    sa.text("SELECT links FROM vacancies WHERE id = 'v1'")
                ).scalar_one()
                is None
            )
            conn.execute(_INSERT, {"id": "v2", "key": "tg:chan/2"})
            conn.execute(
                sa.text("UPDATE vacancies SET links = :links WHERE id = 'v2'"),
                {"links": json.dumps(links)},
            )
            stored = conn.execute(
                sa.text("SELECT links FROM vacancies WHERE id = 'v2'")
            ).scalar_one()
        assert json.loads(stored) == links

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert "links" not in _columns(engine)
        with engine.connect() as conn:
            assert (
                conn.execute(sa.text("SELECT count(*) FROM vacancies")).scalar_one()
                == 2
            )
    finally:
        engine.dispose()
