"""Live smoke test of the discovery evaluator against the real Groq model.

Runs the reference cases of functional spec 009, section 2.2, and the digest
cases of spec 012, section 2.1, and prints a pass table plus token usage and
finish reason per call. Not a pytest test: it costs real quota.

Usage (from backend/; the key is never printed):
    set -a; . ../.env; set +a; python scripts/smoke_evaluator.py
    python scripts/smoke_evaluator.py --env-file ../.env
Env: GROQ_API_KEY (required, from the environment or --env-file),
GROQ_DISCOVERY_MODEL (default openai/gpt-oss-20b; set it to the fallback,
e.g. openai/gpt-oss-120b, to smoke GROQ_DISCOVERY_FALLBACK_MODEL), SMOKE_PAUSE_S (default 30),
SMOKE_DUMP=1 (print the raw JSON answer of every call), SMOKE_SCENARIOS
(comma-separated 1-based scenario numbers to run, default all; 7,8 = digests).
"""

import asyncio
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import groq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.discovery.evaluator import (
    EvaluationError,
    EvaluationRateLimitedError,
    Fit,
    PostVerdict,
    evaluate_batch,
)
from app.discovery.types import RawPost

DEFAULT_MODEL = "openai/gpt-oss-20b"
RATE_LIMIT_WAIT_S = 65

Check = Callable[[PostVerdict], bool]


@dataclass(frozen=True, slots=True)
class Case:
    """A single post (`shown`, `fit`), or any post judged by `check`."""

    text: str
    shown: bool = False
    fit: Fit | None = None
    check: Check | None = None
    expected: str | None = None

    def passes(self, verdict: PostVerdict) -> bool:
        if self.check is not None:
            return self.check(verdict)
        if verdict.is_digest:
            return False
        return verdict.match == self.shown and (
            not self.shown or verdict.fit == self.fit
        )

    def describe(self) -> str:
        if self.expected is not None:
            return self.expected
        return f"shown, {self.fit}" if self.shown else "not shown"


Block = tuple[int, int, Fit | None]


def digest_with(*blocks: Block) -> Check:
    """A digest whose items are exactly one per block: each item's range lies
    inside its block (first..last line) and has the block's fit (None = any)."""

    def check(verdict: PostVerdict) -> bool:
        if not verdict.is_digest or len(verdict.vacancies) != len(blocks):
            return False
        return all(
            first <= item.lines[0] and item.lines[1] <= last and fit in (None, item.fit)
            for item, (first, last, fit) in zip(verdict.vacancies, blocks)
        )

    return check


def nothing_shown(verdict: PostVerdict) -> bool:
    return not verdict.vacancies and not (not verdict.is_digest and verdict.match)


def not_a_digest(verdict: PostVerdict) -> bool:
    return not verdict.is_digest


def digest_items_within(first: int, last: int) -> Check:
    """Not a digest (rated as one post), or a digest listing only lines first..last."""

    def check(verdict: PostVerdict) -> bool:
        return all(
            first <= v.lines[0] and v.lines[1] <= last for v in verdict.vacancies
        )

    return check


@dataclass(frozen=True, slots=True)
class Scenario:
    description: str
    profile: dict[str, object]
    cases: list[Case]


WELLDIN_FULL_POST = "📑 Вакансия Senior Frontend Developer\n\nот $5 000 в месяц · Удалённо из любой страны · Полная занятость\n\n💎 Welldin ищет Senior Frontend Developer для работающего AI-продукта в сфере найма на рынках США и Европы. Предстоит взять на себя фронтенд и определять архитектуру продукта: развивать SPA на React и TypeScript, выбирать стратегию рендеринга, строить модульную архитектуру, создавать интерфейсы с обновлениями в реальном времени, интегрировать внешние API, контролировать производительность и размер бандла, покрывать бизнес-логику тестами. Прямая работа с основателями, минимум бюрократии.\n\n🧩 Требования: От 5 лет опыта во фронтенде, уверенное владение React и TypeScript; понимание event loop, рендеринга и профилирования в браузере; опыт с SSR/SSG, Redux, локальным состоянием и кешированием серверных данных; знание WebSockets, SSE, CORS и браузерной сетевой части; работа со сборщиками webpack, Vite, esbuild или rollup; опыт юнит-тестирования бизнес-логики; умение аргументировать и продвигать технические решения. Плюсом будут микрофронтенды или монорепо, работа с видео и аудио в браузере, разговорный английский и опыт в стартапе на ранней стадии.\n\n\n⚠️ Если работодатель просит войти в их систему через iCloud/Google, прислать код, запустить код/ПО - это мошенники. Обязательно пишите в поддержку."


def _lines(*lines: str) -> str:
    return "\n".join(lines)


# Spec 012 §2.1 reference digest: (1) and (3) match, (2) and (4) do not.
REFERENCE_DIGEST = _lines(
    "Remote and relocation jobs, 22 Nov",  # L1
    "",
    "1) Senior React Developer, remote, €5000",  # L3
    "Acme Corp, React + TypeScript, full-time",
    "",
    "2) Senior Java backend engineer, remote",  # L6
    "Globex, Spring Boot, microservices",
    "",
    "3) Frontend developer (Vue), office in Berlin",  # L9
    "Initech, Vue 3 and Pinia",
    "",
    "4) Product designer, remote",  # L12
    "Umbrella, Figma, design systems",
    "",
    "#jobs #remote",  # L15
    "Post a vacancy: @jobs_admin",
)
NON_IT_DIGEST = _lines(
    "Jobs of the week",
    "",
    "1. Sales manager, Berlin, €3000",
    "2. Customer support agent (German), remote",
    "3. Logistics coordinator, Hamburg warehouse",
    "4. Account executive, B2B sales, remote",
    "5. Support team lead, Lisbon office",
    "6. Truck dispatcher, logistics, remote",
    "",
    "Apply: @hr_jobs_bot",
)
LINK_ONLY_DIGEST = (
    "8 vacancies from OZON 🚀\n"
    "Frontend, backend, QA and analytics roles in Moscow and remote.\n"
    "All vacancies: https://job.ozon.ru/vacancy/"
)
# Real post (2026-11-18, "Digital nomads. Work from anywhere"): a list of job
# categories with counts; the jobs themselves sit behind links.
DIGITAL_NOMADS_DIGEST = _lines(
    "100% remote jobs",
    "18 Nov 07:00 — 19 Nov 07:00 (UTC)",
    "",
    "——Non-IT——",
    "Languages, Translation - 2",
    "",
    "Account Management - 7",
    "Finance & Accounting - 2",
    "Marketplace Management - 3",
    "Recruitment / Talent Acquisition  - 3",
    "Sales & Customer Support - 16",
    "Transportation, Logistics & Shipping - 2",
    "",
    "PR and Marketing, Media Buying - 6",
    "PR and Marketing, Target Ad - 6",
    "",
    "——IT——",
    "AI, AI Engineering - 2",
    "",
    "Back-end, Java - 6",
    "Back-end, Python - 2",
    "",
    "Front-end, Angular - 2",
    "Front-end, React - 3",
    "",
    "IT, DevOps - 2",
    "IT, Product management - 3",
    "IT, QA - 2",
    "IT, QA of software - 2",
    "IT, SAP - 2",
    "",
    "Mobile, Swift (iOS) - 2",
    "",
    "",
    "———",
    "Tired of hunting for remote jobs and applying yourself?",
    "Hire an assistant — turnkey remote job search.",
)

LOCATION_MUST_SEARCH = (
    "Senior / Middle Frontend developer or Full-stack developer, React, Nest js, "
    "Node js, Next js, must be possible to work from Yerevan: on-site/hybrid in "
    "Yerevan, or remote not limited to other countries."
)

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
            # Full live text: the model invented an "expected senior salary" point.
            Case(
                WELLDIN_FULL_POST,
                True,
                Fit.HIGH,
            ),
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
        ],
    ),
    # Spec 012 §2.1 reference digests.
    Scenario(
        description="Senior frontend, React, remote, from 4000 €",
        profile={},
        cases=[
            Case(
                REFERENCE_DIGEST,
                check=digest_with((3, 5, Fit.HIGH), (9, 11, Fit.LOW)),
                expected="digest: (1) L3-5 high, (3) L9-11 low",
            ),
            Case(NON_IT_DIGEST, check=nothing_shown, expected="nothing shown"),
            Case(LINK_ONLY_DIGEST, check=not_a_digest, expected="not a digest"),
        ],
    ),
    # The real digest with the seeker's real description: only the front-end
    # category lines (L23 Angular, L24 React) may become cards, if any.
    Scenario(
        description=(
            "Senior / Middle Frontend developer, Full-stack developer, React, "
            "Nest js, Node js, Next js, Yerevan, remote/hybrid/on-site"
        ),
        profile={},
        cases=[
            Case(
                DIGITAL_NOMADS_DIGEST,
                check=digest_items_within(23, 24),
                expected="one post, or items only in L23-24",
            ),
        ],
    ),
    # The seeker's work-location hard requirement (2026-11-24): a job tied to
    # another country is not shown; an unrestricted remote job or one that does
    # not say where is shown.
    Scenario(
        description=LOCATION_MUST_SEARCH,
        profile={},
        cases=[
            Case(
                "Вакансия Frontend Vue-разработчик. Удалённо из РФ. Lamoda ищет двух "
                "разработчиков в B2B-команду Lamoda Seller.",
                False,
            ),
            Case(
                "Senior React developer, remote within the EU only, "
                "B2B contract, TypeScript, Next.js.",
                False,
            ),
            Case(
                "Middle Frontend developer (React) at a fintech startup. "
                "Office in Dubai, 5 days a week. Visa provided.",
                False,
            ),
            Case(
                "Senior Frontend developer, React + Next.js. Fully remote, work from "
                "any country. Company based in the UAE.",
                check=lambda v: not v.is_digest and v.match,
                expected="shown",
            ),
            Case(
                "Ищем Middle React-разработчика в продуктовую команду. Стек: React, "
                "TypeScript, Node.js. Зарплата по итогам собеседования.",
                check=lambda v: not v.is_digest and v.match,
                expected="shown",
            ),
        ],
    ),
]


def _post(scenario_no: int, case_no: int, text: str) -> RawPost:
    return RawPost(
        # "tg:" so the posts may be digests (see `can_be_digest`).
        external_key=f"tg:smoke/{scenario_no}/{case_no}",
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


class _RecordingClient:
    """Passes calls to the Groq client and keeps the last completion, for the
    finish reason and the token split that `evaluate_batch` does not return."""

    def __init__(self, client: groq.AsyncGroq, *, dump: bool = False) -> None:
        self._client = client
        self._dump = dump
        self.last: Any = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.last = None
        self.last = await self._client.chat.completions.create(**kwargs)
        if self._dump and self.last.choices:
            print(f"  RAW: {self.last.choices[0].message.content}")
        return self.last

    def summary(self) -> str:
        if self.last is None:
            return "no completion"
        usage = self.last.usage
        finish = self.last.choices[0].finish_reason if self.last.choices else None
        return (
            f"prompt={usage.prompt_tokens} completion={usage.completion_tokens} "
            f"total={usage.total_tokens} finish_reason={finish}"
        )


def _got(verdict: PostVerdict) -> str:
    if verdict.is_digest:
        items = ", ".join(
            f"L{v.lines[0]}-{v.lines[1]} {v.fit} ({v.title or '?'})"
            for v in verdict.vacancies
        )
        return f"digest of {verdict.vacancy_count}: {items or 'none listed'}"
    shown = f"shown, {verdict.fit}" if verdict.match else "not shown"
    return f"{shown} (count {verdict.vacancy_count})"


def _short(text: str, limit: int = 70) -> str:
    flat = text.replace("\n", " / ").replace("|", "/")
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


async def main() -> int:
    api_key = os.environ.get("GROQ_API_KEY")
    if "--env-file" in sys.argv:
        api_key = _key_from_env_file(Path(sys.argv[sys.argv.index("--env-file") + 1]))
    if not api_key:
        print("GROQ_API_KEY is not set", file=sys.stderr)
        return 2
    model = os.environ.get("GROQ_DISCOVERY_MODEL", DEFAULT_MODEL)
    pause = float(os.environ.get("SMOKE_PAUSE_S", "30"))
    dump = os.environ.get("SMOKE_DUMP") == "1"
    client = _RecordingClient(groq.AsyncGroq(api_key=api_key, max_retries=0), dump=dump)
    only = {int(n) for n in os.environ.get("SMOKE_SCENARIOS", "").split(",") if n}
    first = True

    rows: list[tuple[str, str, str, str, str, bool]] = []
    for scenario_no, scenario in enumerate(SCENARIOS, start=1):
        if only and scenario_no not in only:
            continue
        if not first:
            await asyncio.sleep(pause)
        first = False
        posts = [
            _post(scenario_no, n, case.text) for n, case in enumerate(scenario.cases)
        ]
        batch = None
        for attempt in (1, 2):
            try:
                batch = await evaluate_batch(
                    client,  # type: ignore[arg-type]
                    model,
                    scenario.description,
                    scenario.profile,
                    posts,
                )
                break
            except EvaluationRateLimitedError as exc:
                print(f"[{scenario.description}] {exc!r}; waiting {RATE_LIMIT_WAIT_S}s")
                if attempt == 2:
                    break
                await asyncio.sleep(RATE_LIMIT_WAIT_S)
            except EvaluationError as exc:
                print(f"[{scenario.description}] evaluation failed: {exc!r}")
                print(f"  {client.summary()}")
                break
        if batch is None:
            for case in scenario.cases:
                rows.append(
                    (
                        scenario.description,
                        _short(case.text),
                        case.describe(),
                        "ERROR",
                        "",
                        False,
                    )
                )
            continue
        print(f"[{scenario_no}: {scenario.description}] {client.summary()}")
        for post, case in zip(posts, scenario.cases):
            verdict = batch.results.get(post.external_key)
            if verdict is None:
                got, reason, ok = "MISSING", "", False
            else:
                got, reason, ok = _got(verdict), verdict.reason, case.passes(verdict)
                for item in verdict.vacancies:
                    print(
                        f"    L{item.lines[0]}-{item.lines[1]} {item.fit}: {item.reason}"
                    )
            rows.append(
                (
                    scenario.description,
                    _short(case.text),
                    case.describe(),
                    got,
                    reason,
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


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
