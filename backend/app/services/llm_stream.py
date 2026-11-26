"""What every chat LLM provider streams back, and how tool-call deltas join.

Shared by the Groq (`groq_client`) and Gemini (`gemini_client`) chat paths:
both stream OpenAI-style chunks, so both yield `str` text chunks and then one
`LlmToolCall` per call, and raise the same two limit errors.
"""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

# Plain aliases: the project still targets Python 3.11 (no `type` statement).
ToolChoice = Literal["auto", "required"]


@dataclass(frozen=True, slots=True)
class LlmToolCall:
    """One tool call from the model, its JSON arguments not yet validated.

    When Groq rejected the model's tool calls (`tool_use_failed`), one call
    with `name` "" stands for them all and `rejected` holds Groq's error
    message (the schema error, e.g. "`/position`: value must be one of ...").
    """

    name: str
    arguments: str
    rejected: str | None = None


# The provider's streaming call (`stream_llm_response` / `stream_gemini_response`).
ChatLlm = Callable[..., AsyncIterator[str | LlmToolCall]]


@dataclass(frozen=True, slots=True)
class LlmLimit:
    """The numbers in a provider's 413/429 message; None for any it does not name.

    E.g. Groq's "... on tokens per minute (TPM): Limit 8000, Requested 9500":
    kind "TPM" (or ITPM, TPD, RPM ...), limit 8000, requested 9500.
    """

    kind: str | None
    limit: int | None
    requested: int | None


NO_LIMIT_NUMBERS = LlmLimit(kind=None, limit=None, requested=None)


class LlmRateLimitError(RuntimeError):
    """429: the model's per-minute (or per-day) quota is used up."""

    def __init__(self, message: str, *, limit: LlmLimit) -> None:
        super().__init__(message)
        self.limit = limit


class LlmRequestTooLargeError(RuntimeError):
    """This one request (input, or input + max_tokens on Groq) is over the
    model's limit (Groq 413, Gemini 400 "input token count ... exceeds")."""

    def __init__(self, message: str, *, limit: LlmLimit) -> None:
        super().__init__(message)
        self.limit = limit


@dataclass(slots=True)
class _CallParts:
    """One tool call being assembled from stream deltas."""

    call_id: str | None
    name: str = ""
    arguments: list[str] = field(default_factory=list)


def _starts_new_call(current: _CallParts, call_id: str | None, name: str) -> bool:
    """A delta at an index already in use begins another call.

    gpt-oss on Groq may send several complete calls under one index; they
    are told apart by a new call id, or (without ids) by a name arriving
    after the current call already has its name and arguments.
    """
    if call_id and current.call_id:
        return call_id != current.call_id
    return bool(name and current.name and "".join(current.arguments))


class CallAssembler:
    """Tool-call deltas keyed by `index`, assembled into calls in order."""

    def __init__(self) -> None:
        self.calls: list[_CallParts] = []
        self._current: dict[int, _CallParts] = {}

    def add(self, index: int, call_id: str | None, name: str, arguments: str) -> None:
        # An empty id (some OpenAI-compatible servers send "") is no id.
        call_id = call_id or None
        current = self._current.get(index)
        if current is None or _starts_new_call(current, call_id, name):
            current = _CallParts(call_id=call_id)
            self._current[index] = current
            self.calls.append(current)
        current.call_id = current.call_id or call_id
        # Some servers repeat the whole name on every delta of a call;
        # OpenAI-style streams send it once (or split, which we join).
        if name and name != current.name:
            current.name += name
        if arguments:
            current.arguments.append(arguments)

    def add_delta(self, delta: Any) -> None:
        """Add every tool-call delta of one OpenAI-style chunk delta.

        A call without an `index` (seen on OpenAI-compatible layers that send
        whole calls) takes its position in the chunk's list.
        """
        for position, call in enumerate(getattr(delta, "tool_calls", None) or []):
            function = getattr(call, "function", None)
            index = getattr(call, "index", None)
            self.add(
                index if isinstance(index, int) else position,
                getattr(call, "id", None),
                (getattr(function, "name", None) or "") if function else "",
                (getattr(function, "arguments", None) or "") if function else "",
            )

    def tool_calls(self) -> list[LlmToolCall]:
        return [
            LlmToolCall(name=parts.name, arguments="".join(parts.arguments))
            for parts in self.calls
        ]


def tool_kwargs(
    tools: list[dict[str, Any]] | None,
    tool_choice: ToolChoice,
    *,
    parallel_tool_calls: bool,
) -> dict[str, Any]:
    """The tool arguments of a chat completion request (none without tools)."""
    if not tools:
        return {}
    kwargs: dict[str, Any] = {"tools": tools, "tool_choice": tool_choice}
    if parallel_tool_calls:
        kwargs["parallel_tool_calls"] = True
    return kwargs
