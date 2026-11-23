"""Tests for app.services.cv_upload (pure text extraction, no endpoint, no DB).

Fixture files are built in memory by ``tests.cv_upload_files``.
"""

import io
import zipfile

import pytest

from app.services.cv_upload import (
    DEFAULT_CV_NAME,
    MAX_CV_NAME_LENGTH,
    MAX_DOCX_UNCOMPRESSED_BYTES,
    MAX_PDF_PAGES,
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    CvUploadError,
    FileTooLarge,
    NoText,
    UnsupportedFile,
    UploadFailed,
    _is_safe_zip,
    cv_name_from_filename,
    extract_cv_text,
    extract_cv_text_async,
    normalize_text,
)
from tests.cv_upload_files import (
    docx_with_merged_cells,
    docx_with_text,
    encrypt_pdf,
    make_docx,
    make_image_only_pdf,
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

    monkeypatch.setattr("app.services.cv_upload.pdf_extract_text", boom)

    with pytest.raises(UploadFailed) as exc_info:
        extract_cv_text(make_pdf([["x"]]), "cv.pdf")

    assert "passwd" not in str(exc_info.value)
    assert exc_info.value.code == "UPLOAD_FAILED"


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
