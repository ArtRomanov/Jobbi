"""In-memory CV upload fixture files, shared by the extraction and endpoint tests.

- PDFs are written by hand (``make_pdf``): a non-embedded font with a
  ``/ToUnicode`` CMap, so Cyrillic text extracts without embedding a font;
- the encrypted PDF is that PDF re-saved by pypdf (dev dependency);
- DOCX files are built with python-docx.
"""

import io
import zipfile
import zlib

from docx import Document
from pypdf import PdfReader, PdfWriter


def make_pdf(pages: list[list[str]], *, padding: int = 0, filter: str = "") -> bytes:
    """Build a minimal text PDF: one list of lines per page.

    Every distinct character gets a one-byte code; a ``/ToUnicode`` CMap maps
    the codes back to Unicode, which is what text extractors read.

    ``padding`` appends that many spaces to each page's content stream;
    ``filter`` ("flate" or "rle") encodes the content streams. Together they
    build decompression bombs: a few hundred KB that decode to many MB.
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
        content = b"\n".join(ops) + b" " * padding
        if filter == "flate":
            content_id = add(
                stream(zlib.compress(content, 9), b"/Filter /FlateDecode ")
            )
        elif filter == "rle":
            content_id = add(stream(_rle_encode(content), b"/Filter /RunLengthDecode "))
        else:
            content_id = add(stream(content))
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


def _rle_encode(data: bytes) -> bytes:
    """RunLengthDecode encoding: a literal run per byte, then full space runs.

    Trailing spaces (the padding) are encoded as runs of 128, so a bomb is
    built fast; it decodes back to exactly ``data``.
    """
    body = data.rstrip(b" ")
    spaces = len(data) - len(body)
    out = bytearray()
    for byte in body:
        out += bytes([0, byte])
    out += bytes([129, 0x20]) * (spaces // 128)
    if spaces % 128:
        out += bytes([0, 0x20]) * (spaces % 128)
    return bytes(out + b"\x80")


def make_image_only_pdf() -> bytes:
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


def encrypt_pdf(data: bytes, password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    writer.encrypt(user_password=password, owner_password=password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_docx() -> bytes:
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


def docx_with_merged_cells() -> bytes:
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


def docx_with_text(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def make_zip(entries: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return out.getvalue()
