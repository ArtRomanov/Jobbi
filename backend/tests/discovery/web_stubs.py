"""A fake job site for web-source worker tests (respx + a stub resolver).

`safe_http` pins every request to the resolved address, so respx sees
`https://<PUBLIC_IP>/<path>`; one route on that host serves every site, and
each site lives under its own path prefix.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import httpx
import respx

from app.discovery.web_scan import web_seen_key

__all__ = ["HOST", "PUBLIC_IP", "Sites", "WebSite", "resolve"]

PUBLIC_IP = "93.184.216.34"
HOST = "jobs.example.com"
HTML = {"content-type": "text/html; charset=utf-8"}


async def resolve(host: str, port: int) -> list[str]:
    """Every host is public (no DNS in tests)."""
    return [PUBLIC_IP]


@dataclass
class JobPage:
    text: str
    title: str | None = None
    company: str | None = None
    posted: datetime | None = None
    status: int = 200


@dataclass
class WebSite:
    """A listing at `/<name>/list` (newest first, `per_page` jobs per page,
    `?page=N`) and job pages at `/<name>/vacancy/<id>`.

    Jobs without a page answer 500. `failing_pages` answer 500 too.
    """

    name: str = "acme"
    per_page: int = 2
    listed: list[str] = field(default_factory=list)
    pages: dict[str, JobPage] = field(default_factory=dict)
    failing_pages: set[int] = field(default_factory=set)
    requests: list[str] = field(default_factory=list)
    on_request: Callable[[httpx.Request], None] | None = None

    @property
    def url(self) -> str:
        return f"https://{HOST}/{self.name}/list"

    def job_url(self, job_id: str) -> str:
        return f"https://{HOST}/{self.name}/vacancy/{job_id}"

    def key(self, source_id: str, job_id: str) -> str:
        return web_seen_key(source_id, self.job_url(job_id))

    def add(self, job_id: str, text: str = "", **kwargs: object) -> None:
        """List `job_id` (newest first: call in listing order) with a page."""
        self.listed.append(job_id)
        self.pages[job_id] = JobPage(text=text or f"Job {job_id}", **kwargs)  # type: ignore[arg-type]

    @property
    def listing_requests(self) -> list[int]:
        return [
            int(r.split("=")[1]) if "=" in r else 1
            for r in self.requests
            if "/list" in r
        ]

    @property
    def job_requests(self) -> list[str]:
        return [r.rsplit("/", 1)[1] for r in self.requests if "/vacancy/" in r]

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        page = int(request.url.params.get("page", "1"))
        self.requests.append(path + (f"?page={page}" if page > 1 else ""))
        if self.on_request is not None:
            self.on_request(request)
        if path.endswith("/list"):
            if page in self.failing_pages:
                return httpx.Response(500)
            return httpx.Response(200, headers=HTML, text=self._listing(page))
        job = self.pages.get(path.rsplit("/", 1)[1])
        if job is None:
            return httpx.Response(500)
        if job.status != 200:
            return httpx.Response(job.status)
        return httpx.Response(200, headers=HTML, text=self._job_html(job))

    def _listing(self, page: int) -> str:
        start = (page - 1) * self.per_page
        ids = self.listed[start : start + self.per_page]
        links = "".join(
            f'<a href="/{self.name}/vacancy/{job_id}"><h3>Listed {job_id}</h3></a>'
            for job_id in ids
        )
        more = len(self.listed) > start + self.per_page
        pager = f'<a rel="next" href="/{self.name}/list?page={page + 1}">next</a>'
        return f"<html><body><main>{links}</main>{pager if more else ''}</body></html>"

    @staticmethod
    def _job_html(job: JobPage) -> str:
        if job.title is None and job.company is None and job.posted is None:
            return f"<html><body><main><p>{job.text}</p></main></body></html>"
        posting: dict[str, object] = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "description": f"<p>{job.text}</p>",
        }
        if job.title is not None:
            posting["title"] = job.title
        if job.company is not None:
            posting["hiringOrganization"] = {
                "@type": "Organization",
                "name": job.company,
            }
        if job.posted is not None:
            posting["datePosted"] = job.posted.isoformat()
        return (
            '<html><head><script type="application/ld+json">'
            f"{json.dumps(posting)}</script></head>"
            f"<body><main><p>{job.text}</p></main></body></html>"
        )


class Sites:
    """Routes the pinned host to the site whose name starts the path."""

    def __init__(self, respx_mock: respx.MockRouter) -> None:
        self.by_name: dict[str, WebSite] = {}
        respx_mock.route(host=PUBLIC_IP).mock(side_effect=self._handle)

    def add(self, site: WebSite) -> WebSite:
        self.by_name[site.name] = site
        return site

    def _handle(self, request: httpx.Request) -> httpx.Response:
        name = request.url.path.strip("/").split("/", 1)[0]
        site = self.by_name.get(name)
        if site is None:
            return httpx.Response(404)
        return site.handle(request)
