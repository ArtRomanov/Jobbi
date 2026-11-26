"""Tool-call parsing: gpt-oss quirks tolerated, every rejection logged.

Live bug: a reply was only "Could not prepare one suggested change." with no
log line saying why the call was rejected.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import chat_service
from app.services.chat_tools import (
    MALFORMED_CALL_NOTE,
    MAX_CARDS_PER_REPLY,
    CallRejection,
    CvEdit,
    check_propose_cv_edit,
    parse_propose_cv_edit,
)
from app.services.groq_client import LlmToolCall, stream_llm_response
from tests.test_chat_cards import (
    APPS,
    _call_chunks,
    _card_count,
    _chunk,
    _fake_groq,
    _h,
    _ScriptedGroq,
    _send,
    _send_failing,
    setup,  # noqa: F401  (fixture)
)

NAME = "propose_cv_edit"
REMOVE = {"op": "remove", "before": "- jQuery"}
SECRET = "SECRET-CV-TEXT"


def _ok(name: str, args: Any) -> CvEdit:
    raw = args if isinstance(args, str) else json.dumps(args)
    result = check_propose_cv_edit(name, raw)
    assert isinstance(result, CvEdit), result
    return result


def _rejected(name: str, raw: str) -> CallRejection:
    result = check_propose_cv_edit(name, raw)
    assert isinstance(result, CallRejection), result
    return result


# ---------------------------------------------------------------------------
# Tool name quirks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "functions.propose_cv_edit",
        "propose_cv_edit<|channel|>commentary",
        "functions.propose_cv_edit<|channel|>commentary json",
        "  propose_cv_edit \n",
    ],
)
def test_name_with_gpt_oss_prefix_or_suffix_is_accepted(name: str) -> None:
    assert _ok(name, REMOVE).op == "remove"


@pytest.mark.parametrize(
    "name", ["update_application", "propose_cv_edits", "functions.other", ""]
)
def test_other_names_are_rejected_as_wrong_name(name: str) -> None:
    assert _rejected(name, json.dumps(REMOVE)).reason == "wrong_name"


# ---------------------------------------------------------------------------
# Argument wrapping quirks
# ---------------------------------------------------------------------------


def test_arguments_wrapped_in_an_arguments_object_are_unwrapped() -> None:
    assert _ok(NAME, {"arguments": REMOVE}).before_text == "- jQuery"


def test_arguments_wrapped_as_a_json_string_inside_arguments() -> None:
    assert _ok(NAME, {"arguments": json.dumps(REMOVE)}).op == "remove"


def test_double_encoded_arguments_are_decoded_once() -> None:
    assert _ok(NAME, json.dumps(json.dumps(REMOVE))).op == "remove"


def test_triple_encoded_arguments_are_not_unwrapped_further() -> None:
    raw = json.dumps(json.dumps(json.dumps(REMOVE)))
    assert _rejected(NAME, raw).reason == "invalid_args"


# ---------------------------------------------------------------------------
# op / position synonyms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("op", "expected"),
    [
        ("update", "replace"),
        ("Edit", "replace"),
        ("REWRITE", "replace"),
        ("modify", "replace"),
        (" Replace ", "replace"),
        ("delete", "remove"),
        ("Remove", "remove"),
    ],
)
def test_op_synonyms_for_replace_and_remove(op: str, expected: str) -> None:
    args: dict[str, Any] = {"op": op, "before": "x"}
    if expected == "replace":
        args["after"] = "y"
    assert _ok(NAME, args).op == expected


@pytest.mark.parametrize("op", ["add", "Append", "INSERT"])
def test_op_synonyms_for_insert(op: str) -> None:
    assert _ok(NAME, {"op": op, "after": "y", "position": "end"}).op == "insert"


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ("Start", "start"),
        ("top", "start"),
        ("Beginning", "start"),
        ("END", "end"),
        ("bottom", "end"),
        ("after", "after_line"),
        ("After_Line", "after_line"),
        ("after-line", "after_line"),
        ("after line", "after_line"),
    ],
)
def test_position_synonyms(position: str, expected: str) -> None:
    args = {"op": "insert", "after": "y", "position": position, "anchor": "x"}
    assert _ok(NAME, args).position == expected


@pytest.mark.parametrize("op", ["rename", "swap", "", "replace_all"])
def test_unknown_op_is_still_invalid(op: str) -> None:
    rejection = _rejected(NAME, json.dumps({"op": op, "before": "x", "after": "y"}))
    assert rejection.reason == "invalid_args"


# ---------------------------------------------------------------------------
# Field-name synonyms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["old", "original", "find"])
def test_before_synonyms(key: str) -> None:
    edit = _ok(NAME, {"op": "replace", key: "x", "after": "y"})
    assert (edit.before_text, edit.after_text) == ("x", "y")


@pytest.mark.parametrize("key", ["new", "text", "replacement"])
def test_after_synonyms(key: str) -> None:
    edit = _ok(NAME, {"op": "replace", "before": "x", key: "y"})
    assert edit.after_text == "y"


def test_a_synonym_never_overrides_the_real_field() -> None:
    edit = _ok(NAME, {"op": "replace", "before": "x", "old": "z", "after": "y"})
    assert edit.before_text == "x"


def test_a_synonym_fills_a_null_real_field() -> None:
    edit = _ok(NAME, {"op": "replace", "before": None, "old": "x", "after": "y"})
    assert edit.before_text == "x"


# ---------------------------------------------------------------------------
# Still rejected, with a reason
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "error_type"),
    [
        ({"op": "replace", "before": "x", "after": "x"}, "replace_no_change"),
        ({"op": "update", "old": "x", "new": "x"}, "replace_no_change"),
        ({"op": "replace", "before": "  ", "after": "y"}, "replace_fields"),
        ({"op": "remove", "before": ""}, "remove_fields"),
        ({"op": "insert", "after": "", "position": "end"}, "insert_fields"),
        ({"op": "insert", "after": "y", "position": "middle"}, "insert_fields"),
        ({"op": "insert", "after": "y", "position": "after"}, "insert_anchor"),
    ],
)
def test_invalid_args_carry_the_error_type(args: dict, error_type: str) -> None:
    rejection = _rejected(NAME, json.dumps(args))
    assert rejection.reason == "invalid_args"
    assert error_type in [e["type"] for e in rejection.log_fields["errors"]]


def test_oversize_text_is_rejected() -> None:
    raw = json.dumps({"op": "replace", "before": "x" * 20_001, "after": "y"})
    rejection = _rejected(NAME, raw)
    assert rejection.reason == "invalid_args"
    assert rejection.log_fields["errors"] == [
        {"loc": ["before"], "type": "string_too_long"}
    ]
    assert rejection.log_fields["before_len"] == 20_001


def test_bad_json_reports_decoder_message_and_position() -> None:
    rejection = _rejected(NAME, '{"op": "remove", "before": ')
    assert rejection.reason == "bad_json"
    assert rejection.log_fields["json_error"] == "Expecting value"
    assert rejection.log_fields["json_pos"] == 27


def test_parse_propose_cv_edit_keeps_its_none_contract() -> None:
    assert parse_propose_cv_edit(NAME, "{bad") is None
    assert parse_propose_cv_edit(NAME, json.dumps(REMOVE)) is not None


# ---------------------------------------------------------------------------
# Log fields: shape only, never argument values
# ---------------------------------------------------------------------------


def test_invalid_args_log_fields_hold_no_values() -> None:
    raw = json.dumps(
        {
            "op": "replace",
            "before": SECRET,
            "after": SECRET,
            "anchor": SECRET + "!",
            SECRET: 1,
        }
    )
    fields = _rejected(NAME, raw).log_fields
    assert fields["op"] == "replace"
    assert fields["before_len"] == len(SECRET)
    assert fields["after_len"] == len(SECRET)
    assert fields["anchor_len"] == len(SECRET) + 1
    assert set(fields["arg_keys"]) == {"op", "before", "after", "anchor", SECRET}
    assert SECRET not in json.dumps(
        {k: v for k, v in fields.items() if k != "arg_keys"}
    )


def test_long_name_and_op_are_truncated() -> None:
    fields = _rejected("x" * 200, json.dumps(REMOVE)).log_fields
    assert fields["name"] == "x" * 64
    fields = _rejected(NAME, json.dumps({"op": "o" * 100, "before": "x"})).log_fields
    assert fields["op"] == "o" * 32


# ---------------------------------------------------------------------------
# The chat logs one warning per rejected call
# ---------------------------------------------------------------------------


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> Any:
    with structlog.testing.capture_logs() as captured:
        monkeypatch.setattr(chat_service, "logger", structlog.get_logger())
        yield captured


def _rejections(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [log for log in logs if log["event"] == "chat_tool_call_rejected"]


async def test_each_rejected_call_logs_one_warning(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    logs: list[dict[str, Any]],
) -> None:
    await _send(
        client,
        setup,
        _chunk("Sure."),
        *_call_chunks(0, '{"op": "replace", "before": "' + SECRET),
        *_call_chunks(1, {"op": "rename", "before": SECRET}),
        *_call_chunks(2, REMOVE),
    )

    found = _rejections(logs)
    assert [log["reason"] for log in found] == ["bad_json", "invalid_args"]
    assert all(log["log_level"] == "warning" for log in found)
    assert found[0]["name"] == NAME
    assert "json_error" in found[0]
    assert found[1]["op"] == "rename"
    assert found[1]["errors"] == [{"loc": ["op"], "type": "literal_error"}]
    assert sorted(found[1]["arg_keys"]) == ["before", "op"]
    assert SECRET not in repr(found)


async def test_calls_over_the_card_limit_are_logged(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    logs: list[dict[str, Any]],
) -> None:
    chunks = [_chunk("Many.")]
    for i in range(MAX_CARDS_PER_REPLY + 1):
        chunks += _call_chunks(i, {"op": "replace", "before": "x", "after": f"y{i}"})

    await _send(client, setup, *chunks)

    assert [log["reason"] for log in _rejections(logs)] == ["over_card_limit"]


# ---------------------------------------------------------------------------
# One retry when every call is rejected by our parser
# ---------------------------------------------------------------------------


async def test_all_calls_rejected_retries_once_with_the_reason(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    db_session: AsyncSession,
    logs: list[dict[str, Any]],
) -> None:
    bad = {"op": "rename", "before": SECRET}
    fake = _ScriptedGroq((_call_chunks(0, bad), None), (_call_chunks(0, REMOVE), None))

    events = await _send_failing(client, setup, fake)

    assert len(fake.calls) == 2
    retry = fake.calls[1]
    assert retry["tool_choice"] == "required"
    nudge = retry["messages"][-1]
    assert nudge["role"] == "system"
    assert "op" in nudge["content"] and "literal_error" in nudge["content"]
    assert SECRET not in json.dumps(retry["messages"][-1])
    # No first-reply text: the retry adds no empty assistant turn.
    assert retry["messages"][-2]["role"] == "user"
    assert [name for name, _ in events] == ["cards", "done"]
    assert await _card_count(db_session) == 1
    assert MALFORMED_CALL_NOTE not in json.dumps(events)
    # The first, rejected call is still logged, once.
    assert [log["op"] for log in _rejections(logs)] == ["rename"]
    assert SECRET not in repr(logs)


async def test_all_calls_rejected_twice_keeps_the_note_and_stops(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    db_session: AsyncSession,
    logs: list[dict[str, Any]],
) -> None:
    bad = {"op": "rename", "before": "x"}
    fake = _ScriptedGroq((_call_chunks(0, bad), None), (_call_chunks(0, bad), None))

    events = await _send_failing(client, setup, fake)

    assert len(fake.calls) == 2
    tokens = "".join(d["text"] for n, d in events if n == "token")
    assert tokens == MALFORMED_CALL_NOTE
    assert await _card_count(db_session) == 0
    # One warning per rejected call: the first one and the retry's.
    assert len(_rejections(logs)) == 2


async def test_retry_without_calls_keeps_the_first_note(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    logs: list[dict[str, Any]],
) -> None:
    bad = {"op": "rename", "before": "x"}
    fake = _ScriptedGroq((_call_chunks(0, bad), None), ([_chunk("Sorry.")], None))

    events = await _send_failing(client, setup, fake)

    tokens = "".join(d["text"] for n, d in events if n == "token")
    assert tokens == f"Sorry.\n\n{MALFORMED_CALL_NOTE}"
    assert len(_rejections(logs)) == 1


async def test_one_valid_call_means_no_retry(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
) -> None:
    _, fake = await _send(
        client,
        setup,
        *_call_chunks(0, {"op": "rename", "before": "x"}),
        *_call_chunks(1, REMOVE),
    )
    assert len(fake.calls) == 1


async def test_all_rejected_retry_skipped_over_budget(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    logs: list[dict[str, Any]],
) -> None:
    bad = {"op": "rename", "before": "x"}
    fake = _ScriptedGroq((_call_chunks(0, bad), None), (_call_chunks(0, REMOVE), None))
    budget = get_settings().CHAT_INPUT_TOKEN_BUDGET

    with patch.object(chat_service, "request_tokens", lambda *a, **k: budget + 1):
        events = await _send_failing(client, setup, fake)

    assert len(fake.calls) == 1
    tokens = "".join(d["text"] for n, d in events if n == "token")
    assert tokens == MALFORMED_CALL_NOTE
    assert len(_rejections(logs)) == 1


# ---------------------------------------------------------------------------
# Stream assembly: several calls under one index (gpt-oss on Groq)
# ---------------------------------------------------------------------------


def _delta(
    index: int,
    *,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> Any:
    return SimpleNamespace(
        index=index,
        id=call_id,
        type="function" if call_id else None,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


async def _collect(*chunks: Any) -> list[LlmToolCall]:
    tools = [{"type": "function", "function": {"name": NAME}}]
    with _fake_groq(*chunks):
        return [
            item
            async for item in stream_llm_response("sys", [], tools=tools)
            if isinstance(item, LlmToolCall)
        ]


async def test_two_complete_calls_under_index_zero_stay_two_calls() -> None:
    first, second = json.dumps(REMOVE), json.dumps({"op": "remove", "before": "y"})
    calls = await _collect(
        _chunk(tool_calls=[_delta(0, call_id="a", name=NAME, arguments=first)]),
        _chunk(tool_calls=[_delta(0, call_id="b", name=NAME, arguments=second)]),
    )
    assert [(c.name, c.arguments) for c in calls] == [(NAME, first), (NAME, second)]


async def test_two_calls_in_one_chunk_under_index_zero_stay_two_calls() -> None:
    first, second = json.dumps(REMOVE), json.dumps({"op": "remove", "before": "y"})
    calls = await _collect(
        _chunk(
            tool_calls=[
                _delta(0, call_id="a", name=NAME, arguments=first),
                _delta(0, call_id="b", name=NAME, arguments=second),
            ]
        ),
    )
    assert [c.arguments for c in calls] == [first, second]


async def test_new_name_after_arguments_without_ids_starts_a_new_call() -> None:
    first, second = json.dumps(REMOVE), json.dumps({"op": "remove", "before": "y"})
    calls = await _collect(
        _chunk(tool_calls=[_delta(0, name=NAME, arguments=first)]),
        _chunk(tool_calls=[_delta(0, name=NAME, arguments=second)]),
    )
    assert [c.arguments for c in calls] == [first, second]


async def test_name_repeated_on_every_delta_is_not_doubled() -> None:
    raw = json.dumps(REMOVE)
    calls = await _collect(
        _chunk(tool_calls=[_delta(0, call_id="a", name=NAME)]),
        _chunk(tool_calls=[_delta(0, call_id="a", name=NAME, arguments=raw[:5])]),
        _chunk(tool_calls=[_delta(0, call_id="a", name=NAME, arguments=raw[5:])]),
    )
    assert [(c.name, c.arguments) for c in calls] == [(NAME, raw)]


async def test_openai_style_split_deltas_still_assemble() -> None:
    raw = json.dumps(REMOVE)
    calls = await _collect(
        _chunk(tool_calls=[_delta(0, call_id="a", name=NAME, arguments="")]),
        _chunk(tool_calls=[_delta(0, arguments=raw[:7])]),
        _chunk(tool_calls=[_delta(1, call_id="b", name=NAME, arguments="")]),
        _chunk(tool_calls=[_delta(0, arguments=raw[7:])]),
        _chunk(tool_calls=[_delta(1, arguments=raw)]),
    )
    assert [c.arguments for c in calls] == [raw, raw]


async def test_chat_gets_two_cards_from_two_calls_under_one_index(
    client: httpx.AsyncClient,
    setup: dict[str, str],  # noqa: F811
    db_session: AsyncSession,
) -> None:
    second = {"op": "remove", "before": "- Kubernetes"}
    with _fake_groq(
        _chunk("Two."),
        _chunk(
            tool_calls=[_delta(0, call_id="a", name=NAME, arguments=json.dumps(REMOVE))]
        ),
        _chunk(
            tool_calls=[_delta(0, call_id="b", name=NAME, arguments=json.dumps(second))]
        ),
    ):
        resp = await client.post(
            f"{APPS}/{setup['app_id']}/chat",
            json={"content": "Edit"},
            headers=_h(setup["token"]),
        )
    assert MALFORMED_CALL_NOTE not in resp.text
    assert await _card_count(db_session) == 2
