"""Tests for ``POST /api/v1/cvs/upload`` (spec 011, section 2.3)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import structlog

from app.api.v1.cv_upload import MAX_UPLOAD_REQUEST_BYTES
from app.services.cv_upload import (
    DEFAULT_CV_NAME,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
)
from tests.cv_upload_files import (
    docx_with_text,
    encrypt_pdf,
    make_docx,
    make_image_only_pdf,
    make_pdf,
    make_zip,
)

URL = "/api/v1/cvs/upload"
CVS_URL = "/api/v1/cvs"
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _upload(
    client: httpx.AsyncClient,
    token: str | None,
    data: bytes,
    filename: str = "cv.pdf",
    mime: str = PDF_MIME,
) -> httpx.Response:
    headers = _auth(token) if token else {}
    return await client.post(
        URL, files={"file": (filename, data, mime)}, headers=headers
    )


async def _list_cvs(client: httpx.AsyncClient, token: str) -> list[dict]:
    resp = await client.get(CVS_URL, headers=_auth(token))
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def token(registered_user: dict) -> str:
    return registered_user["access_token"]


@pytest.fixture
def fail_if_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the test fail if the endpoint gets as far as text extraction."""

    async def _must_not_run(data: bytes, filename: str) -> None:
        raise AssertionError("the upload should be rejected before extraction")

    monkeypatch.setattr("app.api.v1.cv_upload.extract_cv_text_async", _must_not_run)


# --------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------


async def test_upload_pdf_creates_cv(client: httpx.AsyncClient, token: str) -> None:
    data = make_pdf([["Иван Петров", "Python Developer", "Опыт: 7 лет"]])

    resp = await _upload(client, token, data, filename="Иван_CV.pdf")

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Иван_CV"
    assert "Иван Петров" in body["content"]
    assert body["content"].index("Иван") < body["content"].index("Python")
    assert body["became_base"] is False
    assert body["truncated"] is False
    assert body["version"] == 1
    assert body["linked_applications_count"] == 0

    stored = await client.get(f"{CVS_URL}/{body['id']}", headers=_auth(token))
    assert stored.status_code == 200
    assert stored.json()["content"] == body["content"]
    assert stored.json()["name"] == "Иван_CV"


async def test_upload_docx_with_table_creates_cv(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await _upload(client, token, make_docx(), "resume.docx", DOCX_MIME)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "resume"
    content = body["content"]
    for line in ("Иван Петров", "Навыки", "Python, FastAPI", "Опыт работы: 7 лет"):
        assert line in content
    assert content.index("Навыки") < content.index("Опыт работы")
    assert body["truncated"] is False


async def test_upload_type_is_judged_by_content_not_name(
    client: httpx.AsyncClient, token: str
) -> None:
    # A real DOCX sent with a .pdf name and PDF MIME type is still a DOCX.
    resp = await _upload(client, token, make_docx(), "cv.pdf", PDF_MIME)

    assert resp.status_code == 201
    assert "Навыки" in resp.json()["content"]


async def test_long_text_is_cut_and_flagged(
    client: httpx.AsyncClient, token: str
) -> None:
    data = docx_with_text("word " * 5_000)  # 25 000 characters

    resp = await _upload(client, token, data, "long.docx", DOCX_MIME)

    assert resp.status_code == 201
    body = resp.json()
    assert body["truncated"] is True
    assert 0 < len(body["content"]) <= MAX_TEXT_CHARS


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("my resume.final.docx", "my resume.final"),
        ("C:\\Users\\me\\CV 2026.docx", "CV 2026"),
        (".docx", DEFAULT_CV_NAME),
        ("x" * 300 + ".docx", "x" * 255),
    ],
)
async def test_cv_name_comes_from_file_name(
    client: httpx.AsyncClient, token: str, filename: str, expected: str
) -> None:
    resp = await _upload(client, token, make_docx(), filename, DOCX_MIME)

    assert resp.status_code == 201
    assert resp.json()["name"] == expected


# --------------------------------------------------------------------------
# Errors: right code, and no CV created
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "status_code", "code"),
    [
        pytest.param(b"just some text", 415, "UNSUPPORTED_FILE", id="renamed-text"),
        pytest.param(
            make_zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<x/>"}),
            415,
            "UNSUPPORTED_FILE",
            id="zip-not-docx",
        ),
        pytest.param(make_image_only_pdf(), 422, "NO_TEXT", id="scan"),
        pytest.param(
            encrypt_pdf(make_pdf([["Secret CV"]]), "pw"),
            422,
            "NO_TEXT",
            id="encrypted",
        ),
        pytest.param(
            make_zip(
                {"[Content_Types].xml": b"not xml", "word/document.xml": b"<broken"}
            ),
            400,
            "UPLOAD_FAILED",
            id="broken-docx",
        ),
        pytest.param(
            b"%PDF-" + b"0" * MAX_UPLOAD_BYTES, 413, "FILE_TOO_LARGE", id="5mb-plus"
        ),
    ],
)
async def test_bad_file_returns_code_and_creates_no_cv(
    client: httpx.AsyncClient,
    token: str,
    data: bytes,
    status_code: int,
    code: str,
) -> None:
    resp = await _upload(client, token, data, "cv.pdf")

    assert resp.status_code == status_code
    assert resp.json() == {"detail": code}
    assert await _list_cvs(client, token) == []


async def test_file_of_exactly_5_mb_is_not_rejected_for_size(
    client: httpx.AsyncClient, token: str
) -> None:
    # Exactly at the cap: passes the size checks and fails on content instead.
    data = b"x" * MAX_UPLOAD_BYTES

    resp = await _upload(client, token, data, "cv.pdf")

    assert resp.status_code == 415
    assert resp.json() == {"detail": "UNSUPPORTED_FILE"}


async def test_oversized_content_length_is_rejected_before_parsing(
    client: httpx.AsyncClient, token: str, fail_if_extracted: None
) -> None:
    data = b"%PDF-" + b"0" * (MAX_UPLOAD_REQUEST_BYTES + 1)

    resp = await _upload(client, token, data, "big.pdf")

    assert resp.status_code == 413
    assert resp.json() == {"detail": "FILE_TOO_LARGE"}
    assert await _list_cvs(client, token) == []


async def test_oversized_chunked_body_without_content_length_is_rejected(
    client: httpx.AsyncClient, token: str, fail_if_extracted: None
) -> None:
    boundary = "testboundary"
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n%PDF-"
    ).encode()
    chunk = b"0" * (1024 * 1024)

    async def body() -> AsyncIterator[bytes]:
        yield head
        for _ in range(MAX_UPLOAD_REQUEST_BYTES // len(chunk) + 2):
            yield chunk
        yield f"\r\n--{boundary}--\r\n".encode()

    resp = await client.post(
        URL,
        content=body(),
        headers={
            **_auth(token),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    assert "content-length" not in resp.request.headers
    assert resp.status_code == 413
    assert resp.json() == {"detail": "FILE_TOO_LARGE"}
    assert await _list_cvs(client, token) == []


async def test_unexpected_error_is_upload_failed_and_logs_only_the_type(
    client: httpx.AsyncClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _explode(data: bytes, filename: str) -> None:
        raise RuntimeError("Иван Петров, secret CV line")

    monkeypatch.setattr("app.api.v1.cv_upload.extract_cv_text_async", _explode)

    with structlog.testing.capture_logs() as logs:
        # create_app caches loggers on first use; a fresh proxy binds to the
        # capturing config.
        monkeypatch.setattr("app.api.v1.cv_upload.logger", structlog.get_logger())
        resp = await _upload(client, token, make_docx(), "cv.docx", DOCX_MIME)

    assert resp.status_code == 400
    assert resp.json() == {"detail": "UPLOAD_FAILED"}
    assert await _list_cvs(client, token) == []
    failed = [log for log in logs if log["event"] == "cv_upload_failed"]
    assert failed == [
        {
            "event": "cv_upload_failed",
            "error_type": "RuntimeError",
            "log_level": "warning",
        }
    ]
    assert "secret" not in repr(logs)


async def test_missing_file_field_is_rejected(
    client: httpx.AsyncClient, token: str
) -> None:
    resp = await client.post(URL, data={"other": "x"}, headers=_auth(token))

    assert resp.status_code == 422
    assert await _list_cvs(client, token) == []


# --------------------------------------------------------------------------
# Auth and ownership
# --------------------------------------------------------------------------


async def test_upload_requires_auth(client: httpx.AsyncClient, token: str) -> None:
    resp = await _upload(client, None, make_docx(), "cv.docx", DOCX_MIME)

    assert resp.status_code == 401
    assert await _list_cvs(client, token) == []


async def test_uploaded_cv_belongs_to_the_uploader_only(
    client: httpx.AsyncClient, token: str, other_registered_user: dict
) -> None:
    other_token = other_registered_user["access_token"]

    resp = await _upload(client, token, make_docx(), "mine.docx", DOCX_MIME)
    assert resp.status_code == 201
    cv_id = resp.json()["id"]

    assert [cv["id"] for cv in await _list_cvs(client, token)] == [cv_id]
    assert await _list_cvs(client, other_token) == []
    other_get = await client.get(f"{CVS_URL}/{cv_id}", headers=_auth(other_token))
    assert other_get.status_code == 404
