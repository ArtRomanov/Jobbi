"""Migration e6a8c0d2f4b1: `chat_change_cards.op` fits "replace_all" (backlog #34).

Runs the real Alembic CLI against a temporary SQLite file, like
`test_card_warning_migration`.
"""

from pathlib import Path

import sqlalchemy as sa

from tests.test_card_warning_migration import _alembic, _card_ops, _columns

_REVISION = "e6a8c0d2f4b1"
_PREVIOUS = "c3e5a7b9d1f2"


def _insert(engine: sa.Engine, card_id: str, op: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO chat_change_cards "
                "(id, application_id, message_id, cv_id, op, before_text, "
                "after_text, state, created_at) VALUES "
                "(:id, 'a1', 'm1', 'cv1', :op, 'x', 'y', 'pending', "
                "'2026-11-27 12:00:00')"
            ),
            {"id": card_id, "op": op},
        )


def test_upgrade_widens_op_and_downgrade_drops_replace_all_cards(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "migration.db"
    engine = sa.create_engine(f"sqlite:///{db_file}")
    try:
        _alembic(db_file, "upgrade", _PREVIOUS)
        _insert(engine, "c1", "remove")
        assert _columns(engine)["op"]["type"].length == 10

        _alembic(db_file, "upgrade", _REVISION)

        assert _columns(engine)["op"]["type"].length == 16
        _insert(engine, "c2", "replace_all")
        assert sorted(_card_ops(engine)) == ["remove", "replace_all"]

        _alembic(db_file, "downgrade", _PREVIOUS)

        assert _columns(engine)["op"]["type"].length == 10
        assert _card_ops(engine) == ["remove"]
    finally:
        engine.dispose()
