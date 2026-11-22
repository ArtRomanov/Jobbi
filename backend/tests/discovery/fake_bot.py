"""A stand-in for `telegram.Bot` that records `send_message` calls."""

from collections.abc import Callable
from dataclasses import dataclass, field

from telegram.error import BadRequest

# Telegram's limit, counted in UTF-16 code units.
MAX_MESSAGE_LENGTH = 4096


@dataclass
class FakeBot:
    """`errors` are raised by the next calls, one each. `open_transactions`
    (when given) is checked on every call: alerts must not send while a
    database transaction is open."""

    token: str = "123456:SECRET-TOKEN"
    errors: list[Exception] = field(default_factory=list)
    open_transactions: Callable[[], int] | None = None
    attempts: int = 0
    violations: int = 0
    sent: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.attempts += 1
        if self.open_transactions is not None and self.open_transactions():
            self.violations += 1
        if self.errors:
            raise self.errors.pop(0)
        if len(text.encode("utf-16-le")) // 2 > MAX_MESSAGE_LENGTH:
            raise BadRequest("Message is too long")
        self.sent.append((chat_id, text))

    @property
    def texts(self) -> list[str]:
        return [text for _, text in self.sent]
