"""The chat model's one tool: `propose_cv_edit` (spec 011, functional 2.7).

The model never edits the CV. A call only proposes an edit; the backend
validates it here, stores it as a change card, and the user accepts or rejects
it. A call that does not validate is not a card: the chat shows
`MALFORMED_CALL_NOTE` in the assistant reply instead.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.schemas.cv import CV_CONTENT_MAX_CHARS
from app.services.chat_guard_notes import Language

PROPOSE_CV_EDIT = "propose_cv_edit"
MALFORMED_CALL_NOTE = "Could not prepare one suggested change."
# Groq rejected the model's edit calls twice (`tool_use_failed`): no edit of
# that reply survives, so the note speaks for all of them.
REJECTED_CALLS_NOTE: dict[Language, str] = {
    "en": "The AI produced an invalid edit. Please try again or rephrase.",
    "ru": (
        "AI сформировал некорректную правку. Попробуйте ещё раз или "
        "переформулируйте запрос."
    ),
}

# A call whose quoted passage (or anchor) is not in the CV, even read loosely
# (whitespace, dash variants, Markdown markers): Accept could never apply it,
# so it is no card.
PASSAGE_NOT_FOUND_NOTE: dict[Language, str] = {
    "en": (
        "The AI suggested a change but could not point to the exact place in "
        "your CV to change. Please ask again."
    ),
    "ru": (
        "Модель предложила правку, но не смогла точно указать, какое место в "
        "CV изменить. Попросите ещё раз."
    ),
}

# Bounds one reply; extra calls are dropped with the malformed note.
MAX_CARDS_PER_REPLY = 10

PROPOSE_CV_EDIT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": PROPOSE_CV_EDIT,
        "description": (
            "Propose ONE edit to the candidate's CV text. The user sees it as a "
            "card and decides to accept or reject it; nothing changes before "
            "that. Call it once per separate edit; when the user asks for "
            "several changes, call it several times in the same reply. Quote CV "
            "passages exactly as they appear in the CV block, character for "
            "character."
        ),
        # Groq checks every call against this schema and fails the whole reply
        # (`tool_use_failed`) on a mismatch, so the schema only says what it
        # must: field types, nulls allowed, no enums. gpt-oss fills unused
        # fields (`"position": ""` on a replace); `_ProposeCvEditArgs` checks
        # the values per op instead, failing only that one call.
        "parameters": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "description": (
                        'Exactly one of "replace", "insert", "remove", '
                        '"replace_all". replace: swap `before` for `after`. '
                        "remove: delete `before`. insert: add `after` as new "
                        "text at `position`. replace_all: `after` is the "
                        "whole new CV; the reply's only call."
                    ),
                },
                "before": {
                    "type": ["string", "null"],
                    "description": (
                        "replace/remove: the exact passage from the CV, short but "
                        "appearing only once in it."
                    ),
                },
                "after": {
                    "type": ["string", "null"],
                    "description": (
                        "replace/insert: the new text; replace_all: the whole "
                        "new CV. Every fact in it (skill, "
                        "tool, employer, date, number, achievement) must already "
                        "be in the CV or come from the user's messages; never "
                        "take a skill or tool from the job post."
                    ),
                },
                "position": {
                    "type": ["string", "null"],
                    "description": (
                        'insert only, exactly one of "start", "end", "after_line": '
                        "at the start of the CV, at the end, or on a new line "
                        "after the line quoted in `anchor`. Leave it out for "
                        "replace and remove."
                    ),
                },
                "anchor": {
                    "type": ["string", "null"],
                    "description": (
                        "insert with position after_line: an exact, unique quote "
                        "of the CV line the new text goes after."
                    ),
                },
            },
            "required": ["op"],
        },
    },
}

Position = Literal["start", "end", "after_line"]
_POSITIONS: dict[str, Position] = {
    "start": "start",
    "end": "end",
    "after_line": "after_line",
}

# gpt-oss quirks seen or likely on Groq; the values are matched lowercased,
# with "-" and " " read as "_" (`_word`).
_OP_SYNONYMS = {
    "update": "replace",
    "edit": "replace",
    "rewrite": "replace",
    "modify": "replace",
    "delete": "remove",
    "add": "insert",
    "append": "insert",
    "replace_whole": "replace_all",
    "rewrite_all": "replace_all",
    "replace_cv": "replace_all",
}
_POSITION_SYNONYMS: dict[str, Position] = {
    "top": "start",
    "beginning": "start",
    "bottom": "end",
    "after": "after_line",
}
# Field-name synonyms: used only when the real field is missing or null.
_FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "before": ("old", "original", "find"),
    "after": ("new", "text", "replacement"),
}

_Text = Field(default=None, max_length=CV_CONTENT_MAX_CHARS)


class _ProposeCvEditArgs(BaseModel):
    """The arguments of one `propose_cv_edit` call, checked per `op`."""

    model_config = ConfigDict(extra="ignore")

    op: Literal["replace", "insert", "remove", "replace_all"]
    before: str | None = _Text
    after: str | None = _Text
    # Any string: replace and remove ignore it, insert checks it below.
    position: str | None = Field(default=None, max_length=32)
    anchor: str | None = _Text

    @model_validator(mode="before")
    @classmethod
    def _field_synonyms(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for real, synonyms in _FIELD_SYNONYMS.items():
            if data.get(real) is not None:
                continue
            for synonym in synonyms:
                if data.get(synonym) is not None:
                    data[real] = data[synonym]
                    break
        return data

    @field_validator("op", mode="before")
    @classmethod
    def _op_synonym(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        word = _word(value)
        return _OP_SYNONYMS.get(word, word)

    @field_validator("position", mode="before")
    @classmethod
    def _position_synonym(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        word = _word(value)
        return _POSITION_SYNONYMS.get(word, word)

    @model_validator(mode="after")
    def _check_op_fields(self) -> Self:
        # Custom error types: the rejection log names the rule that failed.
        match self.op:
            case "replace":
                if not _has_text(self.before) or self.after is None:
                    raise PydanticCustomError(
                        "replace_fields",
                        "replace needs a non-empty before and an after",
                    )
                if self.before == self.after:
                    raise PydanticCustomError(
                        "replace_no_change", "replace changes nothing"
                    )
            case "remove":
                if not _has_text(self.before):
                    raise PydanticCustomError(
                        "remove_fields", "remove needs a non-empty before"
                    )
            case "insert":
                if not _has_text(self.after) or self.position not in _POSITIONS:
                    raise PydanticCustomError(
                        "insert_fields", "insert needs a non-empty after and a position"
                    )
                if self.position == "after_line" and not _has_text(self.anchor):
                    raise PydanticCustomError(
                        "insert_anchor", "insert after_line needs an anchor"
                    )
            case "replace_all":
                if not _has_text(self.after):
                    raise PydanticCustomError(
                        "replace_all_fields", "replace_all needs the whole CV in after"
                    )
                if not _MARKDOWN_HEADING.search(self.after or ""):
                    raise PydanticCustomError(
                        "replace_all_shape",
                        "replace_all needs the CV in Markdown (# / ## headings)",
                    )
        return self


# A whole-CV edit must be in the CV Markdown shape: at least one `#`/`##`
# heading line. Keeps a stray plain-text draft (or a cut-off scrap) out.
_MARKDOWN_HEADING = re.compile(r"^ {0,3}#{1,2}[ \t]+\S", re.MULTILINE)


def _word(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CvEdit:
    """A validated edit, shaped like a `chat_change_cards` row.

    replace_all: `after_text` is the whole new CV; `before_text` is the CV the
    model saw, filled in by `place_edit` (Accept checks the CV is unchanged).
    """

    op: Literal["replace", "insert", "remove", "replace_all"]
    before_text: str
    after_text: str
    position: Position | None
    anchor_text: str | None
    # Set by the structure check (`cv_structure`) when the edit breaks the
    # CV's sections and the user did not ask for it.
    warning: str | None = None


RejectReason = Literal[
    "wrong_name", "bad_json", "invalid_args", "over_card_limit", "beside_replace_all"
]

# Model output, not user data, but still capped in the log.
_MAX_LOGGED_NAME = 64
_MAX_LOGGED_OP = 32
_MAX_LOGGED_KEY = 32
_MAX_LOGGED_KEYS = 20


@dataclass(frozen=True, slots=True, kw_only=True)
class CallRejection:
    """Why one tool call is not a usable edit.

    `log_fields` describe the call's shape only (name, op, keys, text
    lengths, decoder or pydantic error types); never argument values.
    """

    reason: RejectReason
    log_fields: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """A short, value-free line for the model's retry nudge."""
        match self.reason:
            case "wrong_name":
                return f"the tool name is not {PROPOSE_CV_EDIT}"
            case "bad_json":
                error = self.log_fields.get("json_error", "invalid JSON")
                return f"the arguments are not valid JSON ({error})"
            case "invalid_args":
                parts = [
                    f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['type']}"
                    for e in self.log_fields.get("errors", [])
                ]
                return "invalid arguments (" + "; ".join(parts) + ")"
            case "over_card_limit":
                return f"more than {MAX_CARDS_PER_REPLY} edits in one reply"
            case "beside_replace_all":
                return "an edit in the same reply as replace_all"


def _canonical_name(name: str) -> str:
    """The tool name without gpt-oss's harmony wrapping.

    gpt-oss may leak its channel markup into the name
    (`propose_cv_edit<|channel|>commentary`) or keep the namespace
    (`functions.propose_cv_edit`).
    """
    name = name.split("<|", 1)[0].strip()
    return name.removeprefix("functions.").strip()


def _unwrap(raw: Any) -> Any:
    """Undo one level of each wrapping gpt-oss is known to add.

    A JSON string holding the JSON object (double-encoded), and an object
    holding the real arguments under `arguments`, are each unwrapped once.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return raw
    if isinstance(raw, dict) and "op" not in raw and "arguments" in raw:
        inner = raw["arguments"]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except json.JSONDecodeError:
                return raw
        if isinstance(inner, dict):
            return inner
    return raw


def _shape_fields(raw: Any) -> dict[str, Any]:
    """The call's shape for the log: op, keys and text lengths, no values."""
    if not isinstance(raw, dict):
        return {"args_type": type(raw).__name__}
    fields: dict[str, Any] = {
        "arg_keys": sorted(str(k)[:_MAX_LOGGED_KEY] for k in raw)[:_MAX_LOGGED_KEYS]
    }
    if isinstance(op := raw.get("op"), str):
        fields["op"] = op[:_MAX_LOGGED_OP]
    for key in ("before", "after", "anchor"):
        if isinstance(value := raw.get(key), str):
            fields[f"{key}_len"] = len(value)
    return fields


def check_propose_cv_edit(name: str, arguments: str) -> CvEdit | CallRejection:
    """Validate one tool call: the edit, or why it is not one."""
    logged_name = name[:_MAX_LOGGED_NAME]
    if _canonical_name(name) != PROPOSE_CV_EDIT:
        return CallRejection(reason="wrong_name", log_fields={"name": logged_name})
    try:
        raw = json.loads(arguments)
    except json.JSONDecodeError as e:
        return CallRejection(
            reason="bad_json",
            log_fields={
                "name": logged_name,
                "json_error": e.msg,
                "json_pos": e.pos,
                "args_len": len(arguments),
            },
        )
    raw = _unwrap(raw)
    try:
        args = _ProposeCvEditArgs.model_validate(raw)
    except ValidationError as e:
        errors = [
            {
                "loc": [str(part)[:_MAX_LOGGED_KEY] for part in err["loc"]],
                "type": err["type"],
            }
            for err in e.errors(include_input=False, include_url=False)
        ]
        return CallRejection(
            reason="invalid_args",
            log_fields={"name": logged_name, "errors": errors, **_shape_fields(raw)},
        )
    return _to_edit(args)


def parse_propose_cv_edit(name: str, arguments: str) -> CvEdit | None:
    """Validate one tool call; None when it is not a usable `propose_cv_edit`."""
    result = check_propose_cv_edit(name, arguments)
    return result if isinstance(result, CvEdit) else None


def _to_edit(args: _ProposeCvEditArgs) -> CvEdit:
    match args.op:
        case "replace":
            return CvEdit(
                op="replace",
                before_text=args.before or "",
                after_text=args.after or "",
                position=None,
                anchor_text=None,
            )
        case "remove":
            return CvEdit(
                op="remove",
                before_text=args.before or "",
                after_text="",
                position=None,
                anchor_text=None,
            )
        case "replace_all":
            return CvEdit(
                op="replace_all",
                before_text="",
                after_text=args.after or "",
                position=None,
                anchor_text=None,
            )
        case "insert":
            position = _POSITIONS[args.position or ""]
            is_after_line = position == "after_line"
            return CvEdit(
                op="insert",
                before_text="",
                after_text=args.after or "",
                position=position,
                # The anchor names a line; surrounding whitespace is not part of it.
                anchor_text=(args.anchor or "").strip() if is_after_line else None,
            )
