"""Tests for app.services.cv_upload (pure text extraction, no endpoint, no DB).

Fixture files are built in memory by ``tests.cv_upload_files``.
"""

import io
import zipfile

import pytest
from pdfminer.high_level import extract_text as pdfminer_extract_text
from pdfminer.layout import LAParams

from app.services import cv_upload
from app.services.cv_upload import (
    DEFAULT_CV_NAME,
    MAX_CV_NAME_LENGTH,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_PDF_DECODED_BYTES,
    MAX_PDF_PAGES,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    CvUploadError,
    FileTooLarge,
    NoText,
    PdfDecodeLimitExceeded,
    TextBox,
    UnsupportedFile,
    UploadFailed,
    _is_safe_zip,
    cv_name_from_filename,
    extract_cv_text,
    extract_cv_text_async,
    normalize_text,
    order_text_boxes,
)
from tests.cv_upload_files import (
    TextBlock,
    docx_with_merged_cells,
    docx_with_text,
    encrypt_pdf,
    make_docx,
    make_image_only_pdf,
    make_layout_pdf,
    make_pdf,
    make_zip,
)

# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def test_pdf_text_with_cyrillic_is_extracted() -> None:
    data = make_pdf([["Иван Петров", "Python Developer", "Опыт: 7 лет"]])

    result = extract_cv_text(data, "Иван_CV.pdf")

    assert "Иван Петров" in result.text
    assert "Python Developer" in result.text
    assert "Опыт: 7 лет" in result.text
    assert result.text.index("Иван") < result.text.index("Python")
    assert result.name == "Иван_CV"
    assert result.truncated is False
    assert result.text == result.text.strip()


def test_pdf_reads_at_most_max_pages() -> None:
    pages = [[f"Page marker {i:02d}"] for i in range(MAX_PDF_PAGES + 5)]
    data = make_pdf(pages)

    text = extract_cv_text(data, "cv.pdf").text

    assert "Page marker 00" in text
    assert f"Page marker {MAX_PDF_PAGES - 1:02d}" in text
    assert f"Page marker {MAX_PDF_PAGES:02d}" not in text


def test_image_only_pdf_raises_no_text() -> None:
    with pytest.raises(NoText):
        extract_cv_text(make_image_only_pdf(), "scan.pdf")


def test_encrypted_pdf_raises_no_text() -> None:
    data = encrypt_pdf(make_pdf([["Secret CV"]]), password="s3cret")
    assert b"/Encrypt" in data

    with pytest.raises(NoText):
        extract_cv_text(data, "locked.pdf")


def test_broken_pdf_raises_upload_failed() -> None:
    data = b"%PDF-1.7\n" + b"\x00garbage\xff" * 200

    with pytest.raises(UploadFailed) as exc_info:
        extract_cv_text(data, "broken.pdf")

    assert "garbage" not in str(exc_info.value)


def test_pdf_parser_crash_maps_to_upload_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("internal parser detail /etc/passwd")

    monkeypatch.setattr("app.services.cv_upload.pdf_extract_pages", boom)

    with pytest.raises(UploadFailed) as exc_info:
        extract_cv_text(make_pdf([["x"]]), "cv.pdf")

    assert "passwd" not in str(exc_info.value)
    assert exc_info.value.code == "UPLOAD_FAILED"


# --------------------------------------------------------------------------
# PDF reading order (multi-column layouts are read column by column)
# --------------------------------------------------------------------------

_LEFT, _RIGHT = 72, 340
# Wider than 60% of the 612 pt page: 63 chars * 7.2 pt = 454 pt.
_WIDE_LINE = "Senior Python Developer at Example Corp from 2019 to 2024 Remote"

TWO_COLUMNS: list[TextBlock] = [
    (_LEFT, 700, ["CERTIFICATIONS"]),
    (_RIGHT, 700, ["LANGUAGES"]),
    (_LEFT, 670, ["AWS Solutions Architect", "Kubernetes CKA"]),
    (_RIGHT, 670, ["English fluent", "German basic"]),
]

SECTIONS_AROUND_FULL_WIDTH: list[TextBlock] = [
    (_LEFT, 740, ["SKILLS"]),
    (_RIGHT, 740, ["CONTACTS"]),
    (_LEFT, 710, ["Python FastAPI", "SQLAlchemy"]),
    (_RIGHT, 710, ["mail at example dot com"]),
    (_LEFT, 650, ["EXPERIENCE", _WIDE_LINE]),
    (_LEFT, 590, ["CERTIFICATIONS"]),
    (_RIGHT, 590, ["LANGUAGES"]),
    (_LEFT, 560, ["AWS Solutions Architect", "Kubernetes CKA"]),
    (_RIGHT, 560, ["English fluent", "German basic"]),
]


def _plain_pdfminer_text(data: bytes) -> str:
    return normalize_text(pdfminer_extract_text(io.BytesIO(data), laparams=LAParams()))


def test_two_column_pdf_is_read_column_by_column() -> None:
    text = extract_cv_text(make_layout_pdf([TWO_COLUMNS]), "cv.pdf").text

    assert text == (
        "CERTIFICATIONS\n\nAWS Solutions Architect\nKubernetes CKA\n\n"
        "LANGUAGES\n\nEnglish fluent\nGerman basic"
    )


def test_single_column_pdf_text_is_unchanged() -> None:
    data = make_pdf(
        [
            ["Ivan Petrov", "Python Developer", "", "", "Experience: 7 years"],
            ["Page two", "More text"],
        ]
    )

    assert extract_cv_text(data, "cv.pdf").text == _plain_pdfminer_text(data)


def test_full_width_section_keeps_top_to_bottom_section_order() -> None:
    data = make_layout_pdf([SECTIONS_AROUND_FULL_WIDTH])

    text = extract_cv_text(data, "cv.pdf").text

    assert text == (
        "SKILLS\n\nPython FastAPI\nSQLAlchemy\n\n"
        "CONTACTS\n\nmail at example dot com\n\n"
        f"EXPERIENCE\n{_WIDE_LINE}\n\n"
        "CERTIFICATIONS\n\nAWS Solutions Architect\nKubernetes CKA\n\n"
        "LANGUAGES\n\nEnglish fluent\nGerman basic"
    )


def test_columns_on_several_pages_are_read_page_by_page() -> None:
    data = make_layout_pdf([TWO_COLUMNS, [(_LEFT, 720, ["Page two"])]])

    text = extract_cv_text(data, "cv.pdf").text

    assert text.endswith("LANGUAGES\n\nEnglish fluent\nGerman basic\n\n\nPage two")


@pytest.mark.parametrize(
    "pages",
    [
        pytest.param([TWO_COLUMNS], id="two-columns"),
        pytest.param([SECTIONS_AROUND_FULL_WIDTH], id="full-width-between"),
        pytest.param([TWO_COLUMNS, SECTIONS_AROUND_FULL_WIDTH], id="two-pages"),
    ],
)
def test_reordering_keeps_every_word(pages: list[list[TextBlock]]) -> None:
    data = make_layout_pdf(pages)

    text = extract_cv_text(data, "cv.pdf").text

    assert sorted(text.split()) == sorted(_plain_pdfminer_text(data).split())


def _box(x0: float, x1: float, y1: float, text: str) -> TextBox:
    return TextBox(x0=x0, x1=x1, y1=y1, text=text)


def test_order_text_boxes_reads_three_columns_left_to_right() -> None:
    boxes = [
        _box(400, 550, 700, "C1"),
        _box(40, 180, 700, "A1"),
        _box(220, 360, 700, "B1"),
        _box(40, 180, 650, "A2"),
        _box(400, 550, 650, "C2"),
        _box(220, 360, 650, "B2"),
    ]

    assert order_text_boxes(boxes, page_width=600) == "A1\n\nA2\n\nB1\n\nB2\n\nC1\n\nC2"


def test_order_text_boxes_groups_overlapping_boxes_into_one_column() -> None:
    # "indent" overlaps "head" only partly; "tail" overlaps only the range
    # widened by "indent", so all three end up in one column.
    boxes = [
        _box(300, 400, 700, "right"),
        _box(40, 120, 700, "head"),
        _box(100, 200, 650, "indent"),
        _box(180, 260, 600, "tail"),
    ]

    assert order_text_boxes(boxes, page_width=600) == "head\n\nindent\n\ntail\n\nright"


def test_order_text_boxes_full_width_box_splits_sections() -> None:
    boxes = [
        _box(40, 200, 700, "top left"),
        _box(320, 500, 700, "top right"),
        _box(40, 560, 600, "full width"),
        _box(320, 500, 500, "bottom right"),
        _box(40, 200, 500, "bottom left"),
    ]

    assert order_text_boxes(boxes, page_width=600) == (
        "top left\n\ntop right\n\nfull width\n\nbottom left\n\nbottom right"
    )


def test_order_text_boxes_skips_blank_boxes_and_strips_text() -> None:
    boxes = [_box(40, 200, 700, "  \n"), _box(40, 200, 650, "  body \n")]

    assert order_text_boxes(boxes, page_width=600) == "body"
    assert order_text_boxes([], page_width=600) == ""


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------


def test_docx_paragraphs_and_table_in_document_order() -> None:
    result = extract_cv_text(make_docx(), "Резюме.docx")

    lines = result.text.split("\n")
    assert lines == [
        "Иван Петров",
        "Senior Python Developer",
        "Навыки",
        "Python, FastAPI",
        "Языки",
        "English B2",
        "Опыт работы: 7 лет",
    ]
    assert result.name == "Резюме"
    assert result.truncated is False


def test_docx_merged_cell_is_read_once() -> None:
    text = extract_cv_text(docx_with_merged_cells(), "cv.docx").text

    assert text.count("Merged header") == 1
    assert text.split("\n") == ["Merged header", "Left", "Right"]


def test_docx_whitespace_only_raises_no_text() -> None:
    with pytest.raises(NoText):
        extract_cv_text(docx_with_text("   \t  "), "empty.docx")


def test_zip_without_word_document_is_unsupported() -> None:
    data = make_zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<x/>"})

    with pytest.raises(UnsupportedFile):
        extract_cv_text(data, "sheet.docx")


def test_corrupt_zip_is_unsupported() -> None:
    with pytest.raises(UnsupportedFile):
        extract_cv_text(b"PK\x03\x04" + b"\x00" * 100, "cv.docx")


def test_docx_shaped_zip_with_bad_xml_raises_upload_failed() -> None:
    data = make_zip(
        {"[Content_Types].xml": b"not xml", "word/document.xml": b"<broken"}
    )

    with pytest.raises(UploadFailed):
        extract_cv_text(data, "cv.docx")


def test_zip_bomb_docx_is_rejected_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("python-docx must not open a zip bomb")

    monkeypatch.setattr("app.services.cv_upload.Document", must_not_open)
    real = zipfile.ZipFile(io.BytesIO(make_docx()))
    entries = {name: real.read(name) for name in real.namelist()}
    entries["word/media/bomb.bin"] = b"\x00" * (20 * 1024 * 1024)
    data = make_zip(entries)
    assert len(data) < MAX_UPLOAD_BYTES

    with pytest.raises(UnsupportedFile):
        extract_cv_text(data, "bomb.docx")


def test_zip_total_uncompressed_size_is_capped() -> None:
    half = MAX_DOCX_UNCOMPRESSED_BYTES // 2 + 1
    infos = []
    for name in ("a", "b"):
        info = zipfile.ZipInfo(name)
        info.file_size = half
        info.compress_size = half  # ratio 1: only the total trips the check
        infos.append(info)

    assert _is_safe_zip(infos[:1]) is True
    assert _is_safe_zip(infos) is False


# --------------------------------------------------------------------------
# Sniffing and size
# --------------------------------------------------------------------------


def test_renamed_text_file_is_unsupported() -> None:
    with pytest.raises(UnsupportedFile) as exc_info:
        extract_cv_text(b"Just a plain text CV\n", "cv.pdf")

    assert exc_info.value.code == "UNSUPPORTED_FILE"


def test_real_pdf_with_docx_name_is_read_as_pdf() -> None:
    result = extract_cv_text(make_pdf([["Hello"]]), "cv.docx")

    assert result.text == "Hello"


def test_file_over_5_mb_is_too_large() -> None:
    data = b"%PDF-1.4\n" + b"0" * MAX_UPLOAD_BYTES

    with pytest.raises(FileTooLarge) as exc_info:
        extract_cv_text(data, "big.pdf")

    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_file_of_exactly_5_mb_is_not_too_large() -> None:
    data = b"x" * MAX_UPLOAD_BYTES

    # Passes the size check, then fails sniffing.
    with pytest.raises(UnsupportedFile):
        extract_cv_text(data, "cv.pdf")


def test_error_codes() -> None:
    assert UnsupportedFile.code == "UNSUPPORTED_FILE"
    assert FileTooLarge.code == "FILE_TOO_LARGE"
    assert NoText.code == "NO_TEXT"
    assert UploadFailed.code == "UPLOAD_FAILED"
    for error in (UnsupportedFile, FileTooLarge, NoText, UploadFailed):
        assert issubclass(error, CvUploadError)


# --------------------------------------------------------------------------
# Truncation, normalisation, name
# --------------------------------------------------------------------------


def test_long_text_is_truncated() -> None:
    text = "Опыт " * 5000  # 25 000 characters
    result = extract_cv_text(docx_with_text(text), "cv.docx")

    assert result.truncated is True
    assert len(result.text) <= MAX_TEXT_CHARS
    assert result.text.startswith("Опыт Опыт")


def test_text_of_exactly_max_chars_is_not_truncated() -> None:
    text = "a" * MAX_TEXT_CHARS
    result = extract_cv_text(docx_with_text(text), "cv.docx")

    assert result.truncated is False
    assert result.text == text


def test_normalize_text_only_touches_whitespace() -> None:
    raw = "\n\n  - item one   \r\n**bold**\t\n\n\n\n\nNext\x0cPage two\x00  \n\n"

    assert normalize_text(raw) == "- item one\n**bold**\n\n\nNext\n\nPage two"


def test_normalize_keeps_two_blank_lines() -> None:
    assert normalize_text("a\n\n\nb") == "a\n\n\nb"
    assert normalize_text("a\n\n\n\n\n\nb") == "a\n\n\nb"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("My CV.pdf", "My CV"),
        ("my.cv.final.docx", "my.cv.final"),
        ("  spaced  .pdf", "spaced"),
        (".pdf", DEFAULT_CV_NAME),
        ("", DEFAULT_CV_NAME),
        ("   .docx", DEFAULT_CV_NAME),
        ("noextension", "noextension"),
        ("C:\\fakepath\\Резюме.pdf", "Резюме"),
        ("../../etc/cv.pdf", "cv"),
        ("tab\there.pdf", "tabhere"),
    ],
)
def test_cv_name_from_filename(filename: str, expected: str) -> None:
    assert cv_name_from_filename(filename) == expected


def test_cv_name_is_cut_to_255() -> None:
    name = cv_name_from_filename("я" * 300 + ".pdf")

    assert name == "я" * MAX_CV_NAME_LENGTH


def test_empty_stem_gets_default_name() -> None:
    result = extract_cv_text(make_pdf([["Hello"]]), ".pdf")

    assert result.name == DEFAULT_CV_NAME


# --------------------------------------------------------------------------
# Async wrapper
# --------------------------------------------------------------------------


async def test_async_wrapper_returns_same_result() -> None:
    data = make_docx()

    result = await extract_cv_text_async(data, "cv.docx")

    assert result == extract_cv_text(data, "cv.docx")


async def test_async_wrapper_propagates_errors() -> None:
    with pytest.raises(UnsupportedFile):
        await extract_cv_text_async(b"nope", "cv.pdf")


# --------------------------------------------------------------------------
# PDF decompression bombs (pre-merge F5)
# --------------------------------------------------------------------------

BOMB_PADDING = MAX_PDF_DECODED_BYTES + 1024 * 1024


@pytest.mark.parametrize("filter", ["flate", "rle"])
def test_compressed_pdf_still_extracts(filter: str) -> None:
    data = make_pdf([["Иван Петров", "Python Developer"]], filter=filter)

    assert "Иван Петров" in extract_cv_text(data, "cv.pdf").text


@pytest.mark.parametrize("filter", ["flate", "rle"])
def test_pdf_decompression_bomb_is_rejected_at_the_cap(filter: str) -> None:
    data = make_pdf([["Hello"]], padding=BOMB_PADDING, filter=filter)
    assert len(data) < MAX_UPLOAD_BYTES

    with pytest.raises(UnsupportedFile) as caught:
        extract_cv_text(data, "bomb.pdf")

    # Rejected by the decode cap, not by running out of memory or text
    assert isinstance(caught.value.__cause__, PdfDecodeLimitExceeded)


def test_decode_cap_is_per_document_and_off_outside_extraction() -> None:
    import zlib

    from pdfminer import pdftypes

    big = zlib.compress(b" " * BOMB_PADDING)
    # Outside an extraction pdfminer decodes as usual
    assert len(pdftypes.zlib.decompress(big)) == BOMB_PADDING
    # Two documents under the cap in a row both pass
    small = make_pdf([["Hello"]], padding=MAX_PDF_DECODED_BYTES // 2, filter="flate")
    assert extract_cv_text(small, "a.pdf").text == "Hello"
    assert extract_cv_text(small, "b.pdf").text == "Hello"


# --------------------------------------------------------------------------
# Subprocess isolation (pre-merge F5)
# --------------------------------------------------------------------------


async def test_async_bomb_is_rejected_in_the_worker() -> None:
    data = make_pdf([["Hello"]], padding=BOMB_PADDING, filter="flate")

    with pytest.raises(UnsupportedFile):
        await extract_cv_text_async(data, "bomb.pdf")


async def test_async_worker_timeout_is_upload_failed(monkeypatch) -> None:
    monkeypatch.setattr(cv_upload, "EXTRACT_TIMEOUT_SECONDS", 0.001)

    with pytest.raises(UploadFailed):
        await extract_cv_text_async(make_docx(), "cv.docx")


async def test_async_worker_crash_is_upload_failed(monkeypatch) -> None:
    monkeypatch.setattr(cv_upload, "_WORKER_MODULE", "app.services.no_such_worker")

    with pytest.raises(UploadFailed):
        await extract_cv_text_async(make_docx(), "cv.docx")


async def test_async_too_large_never_starts_a_worker(monkeypatch) -> None:
    monkeypatch.setattr(cv_upload, "_WORKER_MODULE", "app.services.no_such_worker")

    with pytest.raises(FileTooLarge):
        await extract_cv_text_async(b"%PDF-" + b"0" * MAX_UPLOAD_BYTES, "cv.pdf")
