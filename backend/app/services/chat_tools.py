"""The chat model's one tool: `propose_cv_edit` (spec 011, functional 2.7).

The model never edits the CV. A call only proposes an edit; the backend
validates it here, stores it as a change card, and the user accepts or rejects
it. A call that does not validate is not a card: the chat shows
`MALFORMED_CALL_NOTE` in the assistant reply instead.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.schemas.cv import CV_CONTENT_MAX_CHARS

PROPOSE_CV_EDIT = "propose_cv_edit"
MALFORMED_CALL_NOTE = "Could not prepare one suggested change."

# Bounds one reply; extra calls are dropped with the malformed note.
MAX_CARDS_PER_REPLY = 10

PROPOSE_CV_EDIT_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": PROPOSE_CV_EDIT,
        "description": (
            "Propose ONE edit to the candidate's CV text. The user sees it as a "
            "card and decides to accept or reject it; nothing changes before "
            "that. Call it once per separate edit. Quote CV passages exactly as "
            "they appear in the CV block, character for character."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "op": {
                    "type": "string",
                    "enum": ["replace", "insert", "remove"],
                    "description": (
                        "replace: swap `before` for `after`. remove: delete "
                        "`before`. insert: add `after` as new text at `position`."
                    ),
                },
                "before": {
                    "type": "string",
                    "description": (
                        "replace/remove: the exact passage from the CV, short but "
                        "appearing only once in it."
                    ),
                },
                "after": {
                    "type": "string",
                    "description": "replace/insert: the new text.",
                },
                "position": {
                    "type": "string",
                    "enum": ["start", "end", "after_line"],
                    "description": (
                        "insert only: at the start of the CV, at the end, or on a "
                        "new line after the line quoted in `anchor`."
                    ),
                },
                "anchor": {
                    "type": "string",
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

_Text = Field(default=None, max_length=CV_CONTENT_MAX_CHARS)


class _ProposeCvEditArgs(BaseModel):
    """The arguments of one `propose_cv_edit` call, checked per `op`."""

    model_config = ConfigDict(extra="ignore")

    op: Literal["replace", "insert", "remove"]
    before: str | None = _Text
    after: str | None = _Text
    position: Literal["start", "end", "after_line"] | None = None
    anchor: str | None = _Text

    @model_validator(mode="after")
    def _check_op_fields(self) -> Self:
        match self.op:
            case "replace":
                if not _has_text(self.before) or self.after is None:
                    raise ValueError("replace needs a non-empty before and an after")
                if self.before == self.after:
                    raise ValueError("replace changes nothing")
            case "remove":
                if not _has_text(self.before):
                    raise ValueError("remove needs a non-empty before")
            case "insert":
                if not _has_text(self.after) or self.position is None:
                    raise ValueError("insert needs a non-empty after and a position")
                if self.position == "after_line" and not _has_text(self.anchor):
                    raise ValueError("insert after_line needs an anchor")
        return self


def _has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CvEdit:
    """A validated edit, shaped like a `chat_change_cards` row."""

    op: Literal["replace", "insert", "remove"]
    before_text: str
    after_text: str
    position: Literal["start", "end", "after_line"] | None
    anchor_text: str | None


def parse_propose_cv_edit(name: str, arguments: str) -> CvEdit | None:
    """Validate one tool call; None when it is not a usable `propose_cv_edit`."""
    if name != PROPOSE_CV_EDIT:
        return None
    try:
        raw = json.loads(arguments)
        args = _ProposeCvEditArgs.model_validate(raw)
    except (json.JSONDecodeError, ValidationError):
        return None

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
        case "insert":
            is_after_line = args.position == "after_line"
            return CvEdit(
                op="insert",
                before_text="",
                after_text=args.after or "",
                position=args.position,
                # The anchor names a line; surrounding whitespace is not part of it.
                anchor_text=(args.anchor or "").strip() if is_after_line else None,
            )
