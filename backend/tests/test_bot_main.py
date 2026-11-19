"""Bot entry point: logging setup and event loop for run_polling."""

import asyncio
import logging
import threading

import pytest

from app.bot.__main__ import configure_logging, ensure_event_loop

TOKEN_URL = "https://api.telegram.org/bot123456:SECRET-TOKEN/getUpdates"


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    saved = (root.level, list(root.handlers), logging.getLogger("httpx").level)
    yield
    root.setLevel(saved[0])
    root.handlers[:] = saved[1]
    logging.getLogger("httpx").setLevel(saved[2])


def test_httpx_request_urls_with_bot_token_are_not_logged(restore_logging, caplog):
    configure_logging()
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info(
            'HTTP Request: POST %s "HTTP/1.1 200 OK"', TOKEN_URL
        )
        logging.getLogger("app.bot").info("bot log still shows")
    assert "SECRET-TOKEN" not in caplog.text
    assert "bot log still shows" in caplog.text


def test_configure_logging_sets_httpx_to_warning(restore_logging):
    configure_logging()
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING


def test_ensure_event_loop_makes_get_event_loop_work_without_a_loop():
    """PTB 21 run_polling calls asyncio.get_event_loop(), which raises on
    Python 3.14 when no loop is set. Run in a fresh thread: no loop there."""
    result: dict[str, object] = {}

    def worker() -> None:
        try:
            ensure_event_loop()
            loop = asyncio.get_event_loop()
            result["ok"] = not loop.is_closed()
            loop.close()
        except Exception as exc:  # noqa: BLE001 - surfaced via assert below
            result["error"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert result == {"ok": True}
