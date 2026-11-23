"""Tests for app.services.cv_upload (pure text extraction, no endpoint, no DB).

Fixtures are built in memory:
- PDFs are written by hand (``_make_pdf``): a non-embedded font with a
  ``/ToUnicode`` CMap, so Cyrillic text extracts without embedding a font;
- the encrypted PDF is that PDF re-saved by pypdf (dev dependency);
- DOCX files are built with python-docx.
"""

import io
import zipfile

import pytest
from docx import Document
from pypdf import PdfReader, PdfWriter

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

# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------


def _make_pdf(pages: list[list[str]]) -> bytes:
    """Build a minimal text PDF: one list of lines per page.

    Every distinct character gets a one-byte code; a ``/ToUnicode`` CMap maps
    the codes back to Unicode, which is what text extractors read.
    """
    chars = sorted({ch for page in pages for line in page for ch in line})
    if len(chars) > 250:
        raise ValueError("too many distinct characters for a one-byte font")
    codes = {ch: i + 1 for i, ch in enumerate(chars)}

    bfchar = "\n".join(f"<{codes[ch]:02X}> <{ord(ch):04X}>" for ch in chars)
    cmap = (
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /Test-UCS def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(chars)} beginbfchar\n{bfchar}\nendbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode()

    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    def stream(content: bytes, extra: bytes = b"") -> bytes:
        return (
            b"<< /Length %d %s>>\nstream\n" % (len(content), extra)
            + content
            + b"\nendstream"
        )

    catalog_id = add(b"")  # filled below
    pages_id = add(b"")
    cmap_id = add(stream(cmap))
    # Non-standard BaseFont so the explicit /Widths are used: with a standard
    # font (e.g. Helvetica) codes outside its encoding get
    # width 0 and the layout analysis splits words into single letters.
    widths = b" ".join(b"600" for _ in chars)
    font_id = add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /JobbiTestFont "
        b"/FirstChar 1 /LastChar %d /Widths [%s] /ToUnicode %d 0 R >>"
        % (len(chars), widths, cmap_id)
    )
    page_ids: list[int] = []
    for lines in pages:
        ops = [b"BT /F1 12 Tf 72 720 Td 14 TL"]
        for line in lines:
            encoded = "".join(f"{codes[ch]:02X}" for ch in line).encode()
            ops.append(b"<" + encoded + b"> Tj T*")
        ops.append(b"ET")
        content_id = add(stream(b"\n".join(ops)))
        page_ids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_id, font_id, content_id)
            )
        )
    kids = b" ".join(b"%d 0 R" % pid for pid in page_ids)
    objects[catalog_id - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id
    objects[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        kids,
        len(page_ids),
    )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref_at = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog_id, xref_at)
    )
    return out.getvalue()


def _make_image_only_pdf() -> bytes:
    """A page that only paints a filled rectangle: no text objects at all."""
    content = b"0.5 g 72 72 200 200 re f"
    body = b"%PDF-1.4\n" + (
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n"
        % (len(content), content)
    )
    # Let pdfminer rebuild the missing xref table (fallback parser).
    return body + b"trailer\n<< /Root 1 0 R >>\n%%EOF\n"


def _encrypt_pdf(data: bytes, password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=password, owner_password=password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _make_docx() -> bytes:
    document = Document()
    document.add_paragraph("Иван Петров")
    document.add_paragraph("Senior Python Developer")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Навыки"
    table.cell(0, 1).text = "Python, FastAPI"
    table.cell(1, 0).text = "Языки"
    table.cell(1, 1).text = "English B2"
    document.add_paragraph("Опыт работы: 7 лет")
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _docx_with_merged_cells() -> bytes:
    document = Document()
    table = document.add_table(rows=2, cols=2)
    top = table.cell(0, 0).merge(table.cell(0, 1))
    top.text = "Merged header"
    left = table.cell(1, 0)
    left.text = "Left"
    table.cell(1, 1).text = "Right"
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _docx_with_text(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return out.getvalue()


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def test_pdf_text_with_cyrillic_is_extracted() -> None:
    data = _make_pdf([["Иван Петров", "Python Developer", "Опыт: 7 лет"]])

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
    data = _make_pdf(pages)

    text = extract_cv_text(data, "cv.pdf").text

    assert "Page marker 00" in text
    assert f"Page marker {MAX_PDF_PAGES - 1:02d}" in text
    assert f"Page marker {MAX_PDF_PAGES:02d}" not in text


def test_image_only_pdf_raises_no_text() -> None:
    with pytest.raises(NoText):
        extract_cv_text(_make_image_only_pdf(), "scan.pdf")


def test_encrypted_pdf_raises_no_text() -> None:
    data = _encrypt_pdf(_make_pdf([["Secret CV"]]), password="s3cret")
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
        extract_cv_text(_make_pdf([["x"]]), "cv.pdf")

    assert "passwd" not in str(exc_info.value)
    assert exc_info.value.code == "UPLOAD_FAILED"


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------


def test_docx_paragraphs_and_table_in_document_order() -> None:
    result = extract_cv_text(_make_docx(), "Резюме.docx")

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
    text = extract_cv_text(_docx_with_merged_cells(), "cv.docx").text

    assert text.count("Merged header") == 1
    assert text.split("\n") == ["Merged header", "Left", "Right"]


def test_docx_whitespace_only_raises_no_text() -> None:
    with pytest.raises(NoText):
        extract_cv_text(_docx_with_text("   \t  "), "empty.docx")


def test_zip_without_word_document_is_unsupported() -> None:
    data = _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<x/>"})

    with pytest.raises(UnsupportedFile):
        extract_cv_text(data, "sheet.docx")


def test_corrupt_zip_is_unsupported() -> None:
    with pytest.raises(UnsupportedFile):
        extract_cv_text(b"PK\x03\x04" + b"\x00" * 100, "cv.docx")


def test_docx_shaped_zip_with_bad_xml_raises_upload_failed() -> None:
    data = _zip({"[Content_Types].xml": b"not xml", "word/document.xml": b"<broken"})

    with pytest.raises(UploadFailed):
        extract_cv_text(data, "cv.docx")


def test_zip_bomb_docx_is_rejected_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_open(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("python-docx must not open a zip bomb")

    monkeypatch.setattr("app.services.cv_upload.Document", must_not_open)
    real = zipfile.ZipFile(io.BytesIO(_make_docx()))
    entries = {name: real.read(name) for name in real.namelist()}
    entries["word/media/bomb.bin"] = b"\x00" * (20 * 1024 * 1024)
    data = _zip(entries)
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
    result = extract_cv_text(_make_pdf([["Hello"]]), "cv.docx")

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
    result = extract_cv_text(_docx_with_text(text), "cv.docx")

    assert result.truncated is True
    assert len(result.text) <= MAX_TEXT_CHARS
    assert result.text.startswith("Опыт Опыт")


def test_text_of_exactly_max_chars_is_not_truncated() -> None:
    text = "a" * MAX_TEXT_CHARS
    result = extract_cv_text(_docx_with_text(text), "cv.docx")

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
    result = extract_cv_text(_make_pdf([["Hello"]]), ".pdf")

    assert result.name == DEFAULT_CV_NAME


# --------------------------------------------------------------------------
# Async wrapper
# --------------------------------------------------------------------------


async def test_async_wrapper_returns_same_result() -> None:
    data = _make_docx()

    result = await extract_cv_text_async(data, "cv.docx")

    assert result == extract_cv_text(data, "cv.docx")


async def test_async_wrapper_propagates_errors() -> None:
    with pytest.raises(UnsupportedFile):
        await extract_cv_text_async(b"nope", "cv.pdf")
