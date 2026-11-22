"""Share the worker-test fixtures of `test_service.py` with the other worker
test modules in this package (board sources live in `test_board_service.py`)."""

from tests.discovery.test_service import (  # noqa: F401 - re-exported fixtures
    ai,
    db,
    factory,
    http,
    sleep,
)
