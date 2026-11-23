"""Live smoke test of the chat's `propose_cv_edit` tool on the real Groq model.

Sends fixed CV-edit requests through the app's real system prompt and
streaming code (spec 011, slice 7) and prints, per tool call, whether it
validates and whether its quoted passage or anchor occurs exactly once in the
CV, so Accept would apply it. Not a pytest test: it costs real quota.

Usage (from backend/; the key is never printed):
    python scripts/smoke_chat_cards.py --env-file ../.env
    set -a; . ../.env; set +a; python scripts/smoke_chat_cards.py
Env: GROQ_API_KEY (required, from the environment or --env-file), GROQ_MODEL
(the chat model; default from app settings), SMOKE_PAUSE_S (default 5).
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SAMPLE_CV = """# Jane Doe
jane.doe@example.com · +374 00 000000 · Yerevan, Armenia

## Summary
Frontend developer with 7 years of experience building single-page applications \
for fintech and e-commerce companies. I have led small teams, introduced \
TypeScript and automated testing to legacy codebases, and I care deeply about \
accessibility, performance budgets and clean component design across the stack.

## Experience
### Senior Frontend Developer — PayFlow
Mar 2021 – present
- Led the migration of the checkout from AngularJS to React and TypeScript
- Cut the main bundle by 40% with code splitting and lazy routes
- Mentored three junior developers

### Frontend Developer — ShopLine
Jun 2017 – Feb 2021
- Built the storefront UI with jQuery and Handlebars
- Wrote the first end-to-end test suite with Cypress

## Skills
- React, TypeScript, Redux
- Jest, Cypress, Playwright
- Webpack, Vite

## Education
BSc Computer Science — Yerevan State University, 2017
"""

PROMPTS = [
    "Shorten my summary",
    "Add skill Docker to Skills",
    "Remove the line about jQuery",
]


def _from_env_file(path: Path, name: str) -> str | None:
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip().removeprefix("export ").strip() == name:
            return value.strip().strip("'\"") or None
    return None


def _configure_env() -> bool:
    """Put the key (and chat model) in the environment before app imports."""
    if "--env-file" in sys.argv:
        env_file = Path(sys.argv[sys.argv.index("--env-file") + 1])
        for name in ("GROQ_API_KEY", "GROQ_MODEL"):
            value = _from_env_file(env_file, name)
            if value:
                os.environ[name] = value
    os.environ.setdefault("SECRET_KEY", "smoke-only-not-used")
    # The app builds a DB engine at import; never point it at real data.
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
    return bool(os.environ.get("GROQ_API_KEY"))


def _short(text: str, limit: int = 50) -> str:
    flat = " ".join(text.split()).replace("|", "\\|")
    return flat if len(flat) <= limit else flat[:limit] + "…"


async def main() -> int:
    if not _configure_env():
        print("GROQ_API_KEY is not set", file=sys.stderr)
        return 2

    from app.core.config import get_settings
    from app.services.chat_card_service import (
        _PassageMissing,
        _PassageNotUnique,
        apply_card_edit,
    )
    from app.services.chat_tools import PROPOSE_CV_EDIT_TOOL, parse_propose_cv_edit
    from app.services.groq_client import (
        LlmToolCall,
        build_system_prompt,
        stream_llm_response,
    )

    model = get_settings().GROQ_MODEL
    pause = float(os.environ.get("SMOKE_PAUSE_S", "5"))
    application = SimpleNamespace(
        company_name="Acme",
        role_title="Senior Frontend Developer",
        job_url=None,
        status="applied",
        notes=None,
    )
    cv = SimpleNamespace(name="Main CV", content=SAMPLE_CV)
    system_prompt = build_system_prompt(application, cv)  # type: ignore[arg-type]

    rows: list[tuple[str, ...]] = []
    all_ok = True
    for n, prompt in enumerate(PROMPTS):
        if n:
            await asyncio.sleep(pause)
        text: list[str] = []
        calls: list[LlmToolCall] = []
        try:
            async for item in stream_llm_response(
                system_prompt,
                [{"role": "user", "content": prompt}],
                tools=[PROPOSE_CV_EDIT_TOOL],
            ):
                if isinstance(item, LlmToolCall):
                    calls.append(item)
                else:
                    text.append(item)
        except Exception as exc:  # noqa: BLE001 - report any API failure as a row
            rows.append((prompt, "-", "ERROR", type(exc).__name__, "", "", "", ""))
            all_ok = False
            continue

        print(f"[{prompt}] reply: {_short(''.join(text), 2000)!r}")
        if not calls:
            rows.append((prompt, "0", "NO CALL", "", "", "", "", ""))
            all_ok = False
            continue
        for call in calls:
            edit = parse_propose_cv_edit(call.name, call.arguments)
            if edit is None:
                rows.append(
                    (
                        prompt,
                        str(len(calls)),
                        "INVALID",
                        "",
                        "",
                        "",
                        "",
                        _short(call.arguments, 80),
                    )
                )
                all_ok = False
                continue
            quote = edit.anchor_text if edit.op == "insert" else edit.before_text
            occurrences = "-" if not quote else str(SAMPLE_CV.count(quote))
            try:
                apply_card_edit(
                    SAMPLE_CV,
                    op=edit.op,
                    before_text=edit.before_text,
                    after_text=edit.after_text,
                    position=edit.position,
                    anchor_text=edit.anchor_text,
                )
                applies = "yes"
            except _PassageMissing:
                applies = "NO (stale)"
            except _PassageNotUnique:
                applies = "NO (not unique)"
            all_ok = all_ok and applies == "yes"
            rows.append(
                (
                    prompt,
                    str(len(calls)),
                    "valid",
                    f"{edit.op}{'/' + edit.position if edit.position else ''}",
                    _short(quote or ""),
                    occurrences,
                    applies,
                    _short(edit.after_text),
                )
            )

    print()
    print(
        "| Prompt | Calls | Validates | Op | Quote (before/anchor) | Occurs | Applies | After |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(row) + " |")
    print(f"\nmodel {model}: {'all calls usable' if all_ok else 'SOME CALLS FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
