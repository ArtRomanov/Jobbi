"""Run the CV chat eval against the real Groq model (spends tokens).

From `backend/`:

    .venv/bin/python -m evals.cv_chat --label baseline
    .venv/bin/python -m evals.cv_chat --label after --only three_requests russian

Uses the real `stream_chat_response` path and `accept_card` on an in-memory
SQLite database; the app database is never opened. Only GROQ_API_KEY,
GROQ_MODEL and SECRET_KEY are read from the repo-root `.env` (when not already
set in the environment); values are never printed. Writes a JSON file with
every reply, card, score and token count to `evals/cv_chat/results/`, and
prints a table. Stops at the first Groq rate-limit error.

    .venv/bin/python -m evals.cv_chat --rescore evals/cv_chat/results/<file>.json

scores a saved run again with the current scorers, without calling Groq.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
_ENV_KEYS = {"GROQ_API_KEY", "GROQ_MODEL", "SECRET_KEY"}


def _env_file() -> Path | None:
    """The repo-root `.env`; from a git worktree, the nearest one above it."""
    if explicit := os.environ.get("JOBBI_ENV_FILE"):
        return Path(explicit)
    return next((p / ".env" for p in _BACKEND.parents if (p / ".env").is_file()), None)


def _load_env() -> None:
    env_file = _env_file()
    if env_file is not None:
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            key = key.strip()
            if key in _ENV_KEYS and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")
    # The chat never signs tokens; Settings only needs some value.
    os.environ.setdefault("SECRET_KEY", "cv-chat-eval-only")
    # Never the app database: every scenario gets its own in-memory one.
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


_load_env()

import groq
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base
from app.models.application import Application
from app.models.cv import Cv
from app.models.user import User
from app.services import (
    chat_card_service,
    groq_client,
)
from app.services.chat_service import CardsReady, stream_chat_response
from evals.cv_chat.fixtures import COMPANY, CV, ROLE, VACANCY
from evals.cv_chat.scenarios import SCENARIOS
from evals.cv_chat.scoring import (
    Scenario,
    TurnOutcome,
    outline,
    score_scenario,
)

RESULTS = Path(__file__).parent / "results"


class RateLimited(Exception):
    """Groq answered 429: stop the run and report."""


# ---------------------------------------------------------------------------
# Token accounting: wrap the Groq client the app builds
# ---------------------------------------------------------------------------

USAGE: list[dict[str, int]] = []


class _UsageStream:
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def __aiter__(self) -> Any:
        return self._iterate()

    async def _iterate(self) -> Any:
        async for chunk in self._stream:
            x_groq = getattr(chunk, "x_groq", None)
            usage = getattr(x_groq, "usage", None) or getattr(chunk, "usage", None)
            if usage is not None:
                USAGE.append(
                    {
                        "prompt": usage.prompt_tokens,
                        "completion": usage.completion_tokens,
                        "total": usage.total_tokens,
                    }
                )
            yield chunk


_original_get_client = groq_client._get_client


def _client_with_usage() -> groq.AsyncGroq:
    client = _original_get_client()
    create = client.chat.completions.create

    async def _create(**kwargs: Any) -> Any:
        try:
            return _UsageStream(await create(**kwargs))
        except groq.RateLimitError as e:
            raise RateLimited(_redact(str(e))) from e

    client.chat.completions.create = _create  # type: ignore[method-assign]
    return client


def _redact(message: str) -> str:
    return re.sub(r"org_\w+", "org_…", message)


groq_client._get_client = _client_with_usage


# ---------------------------------------------------------------------------
# One scenario
# ---------------------------------------------------------------------------


def _card_dict(card: Any) -> dict[str, str | None]:
    return {
        "op": card.op,
        "before": card.before_text,
        "after": card.after_text,
        "position": card.position,
        "anchor": card.anchor_text,
    }


async def _run_scenario(scenario: Scenario) -> dict[str, Any]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    usage_from = len(USAGE)
    outcomes: list[TurnOutcome] = []
    async with session() as db:
        user = User(email="alex@example.com", password_hash="x", full_name="Alex")
        db.add(user)
        await db.flush()
        cv = Cv(user_id=user.id, name="Alex CV", content=CV, kind="tailored")
        db.add(cv)
        await db.flush()
        application = Application(
            user_id=user.id,
            cv_id=cv.id,
            company_name=COMPANY,
            role_title=ROLE,
            notes=VACANCY,
            status="researching",
        )
        db.add(application)
        await db.flush()
        cv.tailored_for_application_id = application.id
        await db.commit()

        for turn in scenario.turns:
            outcome = TurnOutcome(user=turn.text, reply="")
            reply: list[str] = []
            cards: list[Any] = []
            try:
                async for item in stream_chat_response(db, application, turn.text):
                    if isinstance(item, CardsReady):
                        cards = item.cards
                    else:
                        reply.append(item)
            except RuntimeError as e:
                if isinstance(e.__cause__, groq.RateLimitError):
                    raise RateLimited(_redact(str(e.__cause__))) from e
                raise
            outcome.reply = "".join(reply)
            outcome.cards = [_card_dict(c) for c in cards]
            for card in cards:
                try:
                    await chat_card_service.accept_card(db, application, card.id)
                    outcome.accepted += 1
                except chat_card_service.CardError as e:
                    await db.rollback()
                    outcome.accept_failed.append(f"{e.code}: {card.op}")
            outcomes.append(outcome)

        await db.refresh(cv)
        final = cv.content
    await engine.dispose()

    usage = USAGE[usage_from:]
    scores = score_scenario(
        scenario, outcomes, original=CV, final=final, vacancy=VACANCY
    )
    return {
        "id": scenario.id,
        "scores": scores,
        "tokens": {
            "calls": len(usage),
            "prompt": sum(u["prompt"] for u in usage),
            "completion": sum(u["completion"] for u in usage),
            "total": sum(u["total"] for u in usage),
        },
        "turns": [
            {
                "user": o.user,
                "reply": o.reply,
                "cards": o.cards,
                "accepted": o.accepted,
                "accept_failed": o.accept_failed,
            }
            for o in outcomes
        ],
        "outline_before": outline(CV),
        "outline_after": outline(final),
        "final_cv": final,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _yn(value: object) -> str:
    return "yes" if value else "NO"


def _table(results: list[dict[str, Any]]) -> str:
    header = (
        "| scenario | cards/turn | accepted | requests | did something | "
        "reply~cards | no other tools | no invented | no vacancy-only | tokens | "
        "pass |"
    )
    lines = [header, "|" + "---|" * 11]
    for r in results:
        s = r["scores"]
        cards = "+".join(str(len(t["cards"])) for t in r["turns"])
        accepted = sum(t["accepted"] for t in r["turns"])
        lines.append(
            f"| {r['id']} | {cards} | {accepted} | "
            f"{s['requests_ok']}/{s['requests_total']} | {_yn(s['did_something'])} | "
            f"{_yn(s['reply_matches_cards'])} | {_yn(s['no_foreign_tools'])} | "
            f"{_yn(s['no_invented_facts'])} | "
            f"{_yn(s.get('no_vacancy_only_facts', True))} | {r['tokens']['total']} | "
            f"{_yn(s['passed'])} |"
        )
    total = sum(r["tokens"]["total"] for r in results)
    passed = sum(1 for r in results if r["scores"]["passed"])
    lines.append(f"\npassed {passed}/{len(results)}, tokens {total}")
    return "\n".join(lines)


async def _main(label: str, only: list[str]) -> int:
    scenarios = [s for s in SCENARIOS if not only or s.id in only]
    unknown = set(only) - {s.id for s in SCENARIOS}
    if unknown:
        print(f"unknown scenario(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    results: list[dict[str, Any]] = []
    stopped: str | None = None
    for scenario in scenarios:
        print(f"running {scenario.id} …", flush=True)
        try:
            results.append(await _run_scenario(scenario))
        except RateLimited as e:
            stopped = f"{scenario.id}: {e}"
            print(f"STOPPED, rate limit: {stopped}", file=sys.stderr)
            break

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"{stamp}-{label}.json"
    out.write_text(
        json.dumps(
            {
                "label": label,
                "model": get_settings().GROQ_MODEL,
                "stopped": stopped,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(_table(results))
    print(f"\nsaved {out.relative_to(_BACKEND)}")
    return 1 if stopped else 0


def _rescore(path: Path) -> int:
    """Score a saved run again with the current scorers. No Groq call."""
    data = json.loads(path.read_text())
    by_id = {s.id: s for s in SCENARIOS}
    for result in data["results"]:
        outcomes = [
            TurnOutcome(
                user=t["user"],
                reply=t["reply"],
                cards=t["cards"],
                accepted=t["accepted"],
                accept_failed=t["accept_failed"],
            )
            for t in result["turns"]
        ]
        result["scores"] = score_scenario(
            by_id[result["id"]],
            outcomes,
            original=CV,
            final=result["final_cv"],
            vacancy=VACANCY,
        )
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(_table(data["results"]))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="run", help="name in the results file")
    parser.add_argument("--only", nargs="*", default=[], help="scenario ids")
    parser.add_argument(
        "--rescore", type=Path, help="score a saved results file again (no Groq)"
    )
    args = parser.parse_args()
    if args.rescore:
        sys.exit(_rescore(args.rescore))
    sys.exit(asyncio.run(_main(args.label, args.only)))


if __name__ == "__main__":
    main()
