"""Extract plain text from an uploaded CV file (PDF or DOCX).

Pure, in-memory module: it takes the raw bytes and the client file name and
returns the extracted text plus the CV name. Nothing is written to disk and
no database is touched; the endpoint maps the errors below to HTTP codes.

Rules (spec 011, section 2.3):
- size: more than ``MAX_UPLOAD_BYTES`` -> ``FileTooLarge``;
- type is judged by content, never by the file name:
  - ``%PDF-`` prefix -> PDF;
  - ``PK\\x03\\x04`` zip holding ``[Content_Types].xml`` and
    ``word/document.xml`` -> DOCX;
  - anything else -> ``UnsupportedFile``;
- DOCX zip-bomb guard (before python-docx opens it): total uncompressed size,
  entry count and per-entry compression ratio are capped;
- PDF: pdfminer.six, at most ``MAX_PDF_PAGES`` pages; password-protected ->
  ``NoText``;
- DOCX: python-docx, body walked in order, including table cells;
- text is kept as is (no rewording, no markup); only whitespace is tidied;
  whitespace-only -> ``NoText``; longer than ``MAX_TEXT_CHARS`` -> cut.

Any unexpected parser failure becomes ``UploadFailed`` with a generic message,
so library internals never reach the client.

Extraction is CPU-bound and synchronous; async callers use
``extract_cv_text_async``, which runs it in Starlette's threadpool.
"""

import io
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

import structlog
from docx import Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from pdfminer.high_level import extract_text as pdf_extract_text
from pdfminer.layout import LAParams
from pdfminer.pdfdocument import PDFEncryptionError
from starlette.concurrency import run_in_threadpool

logger = structlog.get_logger()

__all__ = [
    "DEFAULT_CV_NAME",
    "MAX_CV_NAME_LENGTH",
    "MAX_PDF_PAGES",
    "MAX_TEXT_CHARS",
    "MAX_UPLOAD_BYTES",
    "CvUploadError",
    "ExtractedCv",
    "FileTooLarge",
    "NoText",
    "UnsupportedFile",
    "UploadFailed",
    "cv_name_from_filename",
    "extract_cv_text",
    "extract_cv_text_async",
]

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 20_000
MAX_PDF_PAGES = 30
MAX_CV_NAME_LENGTH = 255
DEFAULT_CV_NAME = "Uploaded CV"

# DOCX zip-bomb limits. A real CV .docx unpacks to a few MB at most and its
# XML compresses roughly 5-20x; the ratio check only applies to entries big
# enough to matter, so tiny, highly repetitive parts never trip it.
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_ENTRIES = 1_000
MAX_DOCX_COMPRESSION_RATIO = 100
_RATIO_CHECK_MIN_BYTES = 1024 * 1024

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"
_DOCX_REQUIRED_PARTS = frozenset({"[Content_Types].xml", "word/document.xml"})

_THREE_OR_MORE_BLANK_LINES = re.compile(r"\n{4,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class CvUploadError(Exception):
    """Base for upload errors; ``code`` is the API error code."""

    code: ClassVar[str] = "UPLOAD_FAILED"


class UnsupportedFile(CvUploadError):
    """The content is not a real PDF or DOCX."""

    code: ClassVar[str] = "UNSUPPORTED_FILE"


class FileTooLarge(CvUploadError):
    """The file is larger than ``MAX_UPLOAD_BYTES``."""

    code: ClassVar[str] = "FILE_TOO_LARGE"


class NoText(CvUploadError):
    """No readable text: a scan, an image-only or a password-protected file."""

    code: ClassVar[str] = "NO_TEXT"


class UploadFailed(CvUploadError):
    """Any other failure while reading the file."""

    code: ClassVar[str] = "UPLOAD_FAILED"


@dataclass(frozen=True, slots=True)
class ExtractedCv:
    text: str
    name: str
    truncated: bool


def extract_cv_text(data: bytes, filename: str) -> ExtractedCv:
    """Extract the CV text from ``data`` and derive the CV name from ``filename``.

    Raises:
        FileTooLarge: ``data`` is over ``MAX_UPLOAD_BYTES``.
        UnsupportedFile: the content is neither a PDF nor a DOCX, or the DOCX
            fails the zip-bomb checks.
        NoText: the file holds no readable text or is password-protected.
        UploadFailed: the parser failed for any other reason.
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileTooLarge("The file is larger than 5 MB.")

    if data.startswith(_PDF_MAGIC):
        raw = _extract_pdf(data)
    elif data.startswith(_ZIP_MAGIC):
        raw = _extract_docx(data)
    else:
        raise UnsupportedFile("Upload a PDF or DOCX file.")

    text = normalize_text(raw)
    if not text:
        raise NoText("Could not read text from this file.")

    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS].rstrip()

    return ExtractedCv(
        text=text, name=cv_name_from_filename(filename), truncated=truncated
    )


async def extract_cv_text_async(data: bytes, filename: str) -> ExtractedCv:
    """Run ``extract_cv_text`` in the threadpool so the event loop stays free."""
    return await run_in_threadpool(extract_cv_text, data, filename)


def normalize_text(raw: str) -> str:
    """Tidy whitespace only: never reword, reorder or add markup.

    - line endings become ``\\n``; page breaks (form feeds) become a blank line;
    - NUL bytes are dropped (they break text columns in most databases);
    - trailing whitespace is stripped from every line;
    - three or more blank lines collapse to two;
    - leading and trailing blank space is stripped.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x0c", "\n\n").replace("\x00", "")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _THREE_OR_MORE_BLANK_LINES.sub("\n\n\n", text)
    return text.strip()


def cv_name_from_filename(filename: str) -> str:
    """File name without directories and extension, cut to 255 characters.

    Falls back to ``DEFAULT_CV_NAME`` when nothing is left.
    """
    base = re.split(r"[\\/]", filename)[-1]
    stem, dot, _extension = base.rpartition(".")
    if not dot:
        stem = base
    name = _CONTROL_CHARS.sub("", stem).strip()[:MAX_CV_NAME_LENGTH].strip()
    return name or DEFAULT_CV_NAME


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def _extract_pdf(data: bytes) -> str:
    try:
        return pdf_extract_text(
            io.BytesIO(data), maxpages=MAX_PDF_PAGES, laparams=LAParams()
        )
    except PDFEncryptionError as exc:
        # Wrong/missing password or extraction not allowed.
        raise NoText("Could not read text from this file.") from exc
    # Broad on purpose: any parser bug must map to UPLOAD_FAILED.
    except Exception as exc:
        logger.warning("cv_upload_pdf_parse_failed", error_type=type(exc).__name__)
        raise UploadFailed("Could not upload this file.") from exc


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------


def _check_docx_zip(data: bytes) -> None:
    """Check the zip is a DOCX that is safe to unpack (central directory only)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError) as exc:
        raise UnsupportedFile("Upload a PDF or DOCX file.") from exc

    names = {info.filename for info in infos}
    if not _DOCX_REQUIRED_PARTS <= names:
        raise UnsupportedFile("Upload a PDF or DOCX file.")

    if len(infos) > MAX_DOCX_ENTRIES or not _is_safe_zip(infos):
        logger.warning("cv_upload_docx_zip_rejected", entries=len(infos))
        raise UnsupportedFile("Upload a PDF or DOCX file.")


def _is_safe_zip(infos: list[zipfile.ZipInfo]) -> bool:
    total = 0
    for info in infos:
        total += info.file_size
        if total > MAX_DOCX_UNCOMPRESSED_BYTES:
            return False
        if info.file_size >= _RATIO_CHECK_MIN_BYTES:
            if info.compress_size <= 0:
                return False
            if info.file_size / info.compress_size > MAX_DOCX_COMPRESSION_RATIO:
                return False
    return True


def _extract_docx(data: bytes) -> str:
    # The zip checks run first and only read the central directory; python-docx
    # unpacks nothing until they pass. zipfile also stops each entry at its
    # declared ``file_size``, so the checked sizes are real upper bounds.
    _check_docx_zip(data)
    try:
        document = Document(io.BytesIO(data))
        return "\n".join(_iter_block_lines(document.iter_inner_content()))
    # Broad on purpose: any parser bug must map to UPLOAD_FAILED.
    except Exception as exc:
        logger.warning("cv_upload_docx_parse_failed", error_type=type(exc).__name__)
        raise UploadFailed("Could not upload this file.") from exc


def _iter_block_lines(blocks: Iterator[Paragraph | Table]) -> Iterator[str]:
    """Yield the text of paragraphs and tables in document order."""
    for block in blocks:
        if isinstance(block, Paragraph):
            yield block.text
        else:
            yield from _iter_table_lines(block)


def _iter_table_lines(table: Table) -> Iterator[str]:
    """Cells row by row, left to right; merged cells are read once."""
    # A merged cell (horizontal or vertical) is returned once per grid slot
    # it covers, always backed by the same ``<w:tc>`` element.
    seen: set[object] = set()
    for row in table.rows:
        for cell in row.cells:
            cell_id = cell._tc
            if cell_id in seen:
                continue
            seen.add(cell_id)
            yield from _iter_cell_lines(cell)


def _iter_cell_lines(cell: _Cell) -> Iterator[str]:
    yield from _iter_block_lines(cell.iter_inner_content())
