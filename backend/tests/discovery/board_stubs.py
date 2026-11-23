"""respx stubs for the Greenhouse, Lever and Teamtailor feeds, shared by worker tests."""

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import respx

GH_API = "https://boards-api.greenhouse.io/v1/boards"
LEVER_HOSTS = {"lever": "https://api.lever.co", "lever_eu": "https://api.eu.lever.co"}

Hook = Callable[[httpx.Request], None]


@dataclass
class GreenhouseBoard:
    """Serves `/jobs` (list without content) and `/jobs/<id>` for one token.

    `jobs[id] = (title, text, first_published or None)`. `fail_list` makes the
    listing answer with that status; `missing_details` 404 and
    `failing_details` 503 on the detail.
    """

    token: str = "acme"
    name: str = "Acme Corp"
    jobs: dict[int, tuple[str, str, datetime | None]] = field(default_factory=dict)
    fail_list: int | None = None
    missing_details: set[int] = field(default_factory=set)
    failing_details: set[int] = field(default_factory=set)  # answer 503
    list_requests: int = 0
    detail_requests: list[int] = field(default_factory=list)
    on_request: Hook | None = None

    def add(
        self, job_id: int, text: str, published: datetime | None, title: str = "Dev"
    ) -> None:
        self.jobs[job_id] = (title, text, published)

    def mount(self, router: respx.MockRouter) -> None:
        base = f"{GH_API}/{self.token}"
        router.get(f"{base}/jobs").mock(side_effect=self._list)
        router.get(url__regex=rf"^{re.escape(base)}/jobs/(?P<job_id>\d+)$").mock(
            side_effect=self._detail
        )

    def _list(self, request: httpx.Request) -> httpx.Response:
        if self.on_request is not None:
            self.on_request(request)
        self.list_requests += 1
        if self.fail_list is not None:
            return httpx.Response(self.fail_list)
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": job_id,
                        "title": title,
                        "absolute_url": (
                            f"https://job-boards.greenhouse.io/{self.token}/jobs/{job_id}"
                            "?utm_source=x"
                        ),
                        "location": {"name": "Remote"},
                        "first_published": (
                            published.replace(tzinfo=UTC).isoformat()
                            if published
                            else None
                        ),
                        "updated_at": None,
                        "company_name": self.name,
                    }
                    for job_id, (title, _, published) in self.jobs.items()
                ],
                "meta": {"total": len(self.jobs)},
            },
        )

    def _detail(self, request: httpx.Request, job_id: str) -> httpx.Response:
        if self.on_request is not None:
            self.on_request(request)
        self.detail_requests.append(int(job_id))
        if int(job_id) in self.failing_details:
            return httpx.Response(503)
        if int(job_id) in self.missing_details or int(job_id) not in self.jobs:
            return httpx.Response(404, json={"status": 404})
        _, text, _ = self.jobs[int(job_id)]
        return httpx.Response(
            200, json={"id": int(job_id), "content": html.escape(f"<p>{text}</p>")}
        )


@dataclass
class LeverBoard:
    """Serves `/v0/postings/<company>?mode=json&limit&skip` for one region.

    `postings[id] = (title, text, createdAt or None)`.
    """

    company: str = "acme-labs"
    kind: str = "lever"
    postings: dict[str, tuple[str, str, datetime | None]] = field(default_factory=dict)
    status: int = 200
    requests: list[tuple[int, int]] = field(default_factory=list)  # (skip, limit)
    on_request: Hook | None = None

    def add(
        self, posting_id: str, text: str, created: datetime | None, title: str = "Dev"
    ) -> None:
        self.postings[posting_id] = (title, text, created)

    @property
    def url(self) -> str:
        return f"{LEVER_HOSTS[self.kind]}/v0/postings/{self.company}"

    def mount(self, router: respx.MockRouter) -> None:
        router.get(self.url).mock(side_effect=self._list)

    def _list(self, request: httpx.Request) -> httpx.Response:
        if self.on_request is not None:
            self.on_request(request)
        skip = int(request.url.params.get("skip", "0"))
        limit = int(request.url.params.get("limit", "100"))
        self.requests.append((skip, limit))
        if self.status != 200:
            return httpx.Response(self.status)
        region = "jobs.eu.lever.co" if self.kind == "lever_eu" else "jobs.lever.co"
        items = list(self.postings.items())[skip : skip + limit]
        return httpx.Response(
            200,
            json=[
                {
                    "id": posting_id,
                    "text": title,
                    "hostedUrl": f"https://{region}/{self.company}/{posting_id}",
                    "descriptionPlain": text,
                    "lists": [],
                    **(
                        {
                            "createdAt": int(
                                created.replace(tzinfo=UTC).timestamp() * 1000
                            )
                        }
                        if created
                        else {}
                    ),
                }
                for posting_id, (title, text, created) in items
            ],
        )


@dataclass
class TeamtailorBoard:
    """Serves `https://<sub>.teamtailor.com/jobs.rss`.

    `jobs[id] = (title, text, pubDate or None)`.
    """

    subdomain: str = "acme"
    name: str = "Acme AB"
    jobs: dict[int, tuple[str, str, datetime | None]] = field(default_factory=dict)
    status: int = 200
    requests: int = 0
    on_request: Hook | None = None

    def add(
        self, job_id: int, text: str, published: datetime | None, title: str = "Dev"
    ) -> None:
        self.jobs[job_id] = (title, text, published)

    @property
    def url(self) -> str:
        return f"https://{self.subdomain}.teamtailor.com/jobs.rss"

    def mount(self, router: respx.MockRouter) -> None:
        router.get(self.url).mock(side_effect=self._feed)

    def _feed(self, request: httpx.Request) -> httpx.Response:
        if self.on_request is not None:
            self.on_request(request)
        self.requests += 1
        if self.status != 200:
            return httpx.Response(self.status)
        items = "".join(
            "<item>"
            f"<title>{html.escape(title)}</title>"
            f"<link>https://{self.subdomain}.teamtailor.com/jobs/{job_id}-dev</link>"
            + (
                f"<pubDate>{format_datetime(published.replace(tzinfo=UTC))}</pubDate>"
                if published
                else ""
            )
            + f"<description>{html.escape(f'<p>{text}</p>')}</description>"
            "</item>"
            for job_id, (title, text, published) in self.jobs.items()
        )
        body = (
            '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>{html.escape(self.name)}</title>{items}</channel></rss>"
        )
        return httpx.Response(
            200, content=body.encode(), headers={"Content-Type": "application/rss+xml"}
        )
