"""Live smoke test of the discovery evaluator against the real Groq model.

Runs the reference cases of functional spec 009, section 2.2, and prints a pass
table plus token usage per call. Not a pytest test: it costs real quota.

Usage (from backend/; the key is never printed):
    set -a; . ../.env; set +a; python scripts/smoke_evaluator.py
    python scripts/smoke_evaluator.py --env-file ../.env
Env: GROQ_API_KEY (required, from the environment or --env-file),
GROQ_DISCOVERY_MODEL (default qwen/qwen3.8-27b), SMOKE_PAUSE_S (default 30).
"""

import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import groq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.discovery.evaluator import (
    EvaluationError,
    Fit,
    evaluate_batch,
)
from app.discovery.types import RawPost

DEFAULT_MODEL = "qwen/qwen3.8-27b"


@dataclass(frozen=True, slots=True)
class Case:
    text: str
    shown: bool
    fit: Fit | None


@dataclass(frozen=True, slots=True)
class Scenario:
    description: str
    profile: dict[str, object]
    cases: list[Case]


SCENARIOS = [
    Scenario(
        description="Senior frontend, React, remote, from 4000 €",
        profile={},
        cases=[
            Case("Senior React Developer, fully remote, €5000–6000", True, Fit.HIGH),
            Case("Senior React Developer, remote, salary not stated", True, Fit.MEDIUM),
            Case(
                "Frontend developer (Vue), office in Berlin, salary not stated",
                True,
                Fit.LOW,
            ),
            Case("Our channel turns 5 years old today!", False, None),
            Case("Senior Java backend engineer, remote", False, None),
        ],
    ),
    Scenario(
        description="Frontend, remote only",
        profile={},
        cases=[Case("Frontend developer, office in Berlin", False, None)],
    ),
    Scenario(
        description="Senior frontend, React",
        profile={"salary_min": 6000, "salary_currency": "EUR"},
        cases=[Case("Senior React Developer, €4000", True, Fit.MEDIUM)],
    ),
    # Live 2026-11-22: a plain "remote" was treated as a hard requirement.
    Scenario(
        description="Frontend developer, React, remote",
        profile={},
        cases=[
            Case("Frontend Developer, office in Sofia, React", True, Fit.MEDIUM),
            Case("Full Stack developer (React + Node), remote", False, None),
        ],
    ),
    # Live 2026-11-23 (@frontend_jobs_vakansii): every listed technology and the
    # city were treated as separate must-haves, so remote React jobs got Medium.
    Scenario(
        description=(
            "Senior / Middle Frontend developer, Full-stack developer, React, "
            "Nest js, Node js, Next js, Yerevan, remote/hybrid/on-site"
        ),
        profile={},
        cases=[
            Case(
                "Вакансия Senior Frontend Developer. от $5 000 в месяц · Удалённо из "
                "любой страны · Полная занятость. Welldin: SPA на React и TypeScript, "
                "SSR/SSG, Redux, WebSockets. От 5 лет опыта во фронтенде.",
                True,
                Fit.HIGH,
            ),
            Case(
                "Вакансия Senior Frontend Engineer. Удалённо · Полная занятость. "
                "Squads (финтех, Solana): UI-компоненты, дизайн-система. От 5 лет "
                "опыта, React, Next.js, TypeScript.",
                True,
                Fit.HIGH,
            ),
            Case(
                "Вакансия Frontend Developer (React / Django). Удаленно · Полная "
                "занятость. Multivision: React-приложения на TypeScript и шаблоны "
                "Django/Jinja. Опыт уровня Mid-Level в React, TypeScript, Django.",
                True,
                Fit.HIGH,
            ),
            Case(
                "Вакансия Middle+/Senior Frontend Developer (Vue). Удалённо · Полная "
                "занятость. Napoleon IT: Vue 3, Composition API, TypeScript, Pinia, "
                "Vite. Опыт от 5 лет.",
                True,
                Fit.MEDIUM,
            ),
        ],
    ),
    # Same description, second batch (BATCH_SIZE is 5).
    Scenario(
        description=(
            "Senior / Middle Frontend developer, Full-stack developer, React, "
            "Nest js, Node js, Next js, Yerevan, remote/hybrid/on-site"
        ),
        profile={},
        cases=[
            Case(
                "Вакансия Frontend Vue-разработчик. Удалённо из РФ. Lamoda ищет двух "
                "разработчиков в B2B-команду Lamoda Seller.",
                True,
                Fit.LOW,
            ),
            Case(
                "Вакансия Frontend / Game Client разработчик. от 4000$ · Удалённо · "
                "Полная занятость. CrownWave Tech: игровой клиент на TypeScript и "
                "Cocos Creator, iGaming.",
                True,
                Fit.MEDIUM,
            ),
            Case(
                "Вакансия CRO / Experimentation Developer (Dynamic Yield). от 15 до "
                "20 € в час · Удалённо, требуется ВНЖ ЕС. A/B-тесты и персонализация "
                "в Dynamic Yield.",
                False,
                None,
            ),
        ],
    ),
]


def _post(scenario_no: int, case_no: int, text: str) -> RawPost:
    return RawPost(
        external_key=f"smoke:{scenario_no}/{case_no}",
        url=f"https://t.me/smoke/{scenario_no}{case_no}",
        job_link=None,
        title=None,
        company=None,
        text=text,
        posted_at=datetime(2026, 11, 22, 12, 0),
    )


def _key_from_env_file(path: Path) -> str | None:
    for line in path.read_text().splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name.strip().removeprefix("export ").strip() == "GROQ_API_KEY":
            return value.strip().strip("'\"") or None
    return None


async def main() -> int:
    api_key = os.environ.get("GROQ_API_KEY")
    if "--env-file" in sys.argv:
        api_key = _key_from_env_file(Path(sys.argv[sys.argv.index("--env-file") + 1]))
    if not api_key:
        print("GROQ_API_KEY is not set", file=sys.stderr)
        return 2
    model = os.environ.get("GROQ_DISCOVERY_MODEL", DEFAULT_MODEL)
    pause = float(os.environ.get("SMOKE_PAUSE_S", "30"))
    client = groq.AsyncGroq(api_key=api_key, max_retries=0)

    rows: list[tuple[str, str, str, str, str, bool]] = []
    for scenario_no, scenario in enumerate(SCENARIOS, start=1):
        if scenario_no > 1:
            await asyncio.sleep(pause)
        posts = [
            _post(scenario_no, n, case.text) for n, case in enumerate(scenario.cases)
        ]
        try:
            batch = await evaluate_batch(
                client, model, scenario.description, scenario.profile, posts
            )
        except EvaluationError as exc:
            print(f"[{scenario.description}] evaluation failed: {exc!r}")
            for case in scenario.cases:
                rows.append(
                    (
                        scenario.description,
                        case.text,
                        _expected(case),
                        "ERROR",
                        "",
                        False,
                    )
                )
            continue
        print(f"[{scenario.description}] total_tokens={batch.total_tokens}")
        for post, case in zip(posts, scenario.cases):
            verdict = batch.results.get(post.external_key)
            if verdict is None:
                rows.append(
                    (
                        scenario.description,
                        case.text,
                        _expected(case),
                        "MISSING",
                        "",
                        False,
                    )
                )
                continue
            shown = verdict.match
            got = f"shown, {verdict.fit}" if shown else "not shown"
            ok = shown == case.shown and (not shown or verdict.fit == case.fit)
            rows.append(
                (
                    scenario.description,
                    case.text,
                    _expected(case),
                    got,
                    verdict.reason,
                    ok,
                )
            )

    print()
    print("| Description | Post | Expected | Got | Pass | Reason |")
    print("|---|---|---|---|---|---|")
    for description, text, expected, got, reason, ok in rows:
        print(
            f"| {description} | {text} | {expected} | {got} | {'yes' if ok else 'NO'} | {reason} |"
        )
    passed = sum(row[-1] for row in rows)
    print(f"\n{passed}/{len(rows)} passed (model {model})")
    return 0 if passed == len(rows) else 1


def _expected(case: Case) -> str:
    return f"shown, {case.fit}" if case.shown else "not shown"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
