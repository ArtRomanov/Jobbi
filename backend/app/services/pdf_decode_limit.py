"""Cap how many bytes pdfminer may decode from the streams of one PDF.

A PDF stream can be compressed far beyond any zip ratio check: a few hundred
KB of FlateDecode data can inflate to hundreds of MB. pdfminer decodes each
stream in full (``PDFStream.decode``), with no size limit.

``install()`` swaps the decoders pdfminer's ``pdftypes`` module looks up at
call time (``zlib``, ``lzwdecode``, ``rldecode``) for capped versions. They
behave exactly like the originals unless a budget is active: inside
``decode_budget(limit)`` every decoded byte of every stream is counted, output
is produced at most one byte past the remaining budget, and going over raises
``PdfDecodeLimitExceeded``. The budget lives in a ContextVar, so threads
extracting different files do not share it.
"""

import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from typing import Any

from pdfminer import pdftypes
from pdfminer.lzw import LZWDecoder

__all__ = ["DecodeBudget", "PdfDecodeLimitExceeded", "decode_budget", "install"]


class PdfDecodeLimitExceeded(Exception):
    """The PDF's streams decode to more than the allowed number of bytes."""


class DecodeBudget:
    """Bytes still allowed to be decoded for the current document."""

    def __init__(self, limit: int) -> None:
        self.remaining = limit
        self.exceeded = False

    def take(self, size: int) -> None:
        if size > self.remaining:
            self.exceeded = True
            raise PdfDecodeLimitExceeded
        self.remaining -= size


_budget: ContextVar[DecodeBudget | None] = ContextVar("pdf_decode_budget", default=None)


@contextmanager
def decode_budget(limit: int) -> Iterator[DecodeBudget]:
    """Count every byte pdfminer decodes inside the block against `limit`.

    The caller checks ``budget.exceeded`` afterwards too: pdfminer may catch
    the error somewhere and carry on.
    """
    budget = DecodeBudget(limit)
    token = _budget.set(budget)
    try:
        yield budget
    finally:
        _budget.reset(token)


class _CappedDecompressObj:
    def __init__(self, budget: DecodeBudget) -> None:
        self._inner = zlib.decompressobj()
        self._budget = budget

    def decompress(self, data: bytes, max_length: int = 0) -> bytes:
        cap = self._budget.remaining + 1
        out = self._inner.decompress(data, min(max_length or cap, cap))
        self._budget.take(len(out))
        return out

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _CappedZlib:
    """Stands in for the ``zlib`` module inside ``pdfminer.pdftypes``."""

    error = zlib.error

    @staticmethod
    def decompress(data: bytes) -> bytes:
        budget = _budget.get()
        if budget is None:
            return zlib.decompress(data)
        inflater = zlib.decompressobj()
        out = inflater.decompress(data, budget.remaining + 1)
        budget.take(len(out))
        if not inflater.eof:
            # Same as zlib.decompress on a truncated stream; pdfminer then
            # tries its byte-by-byte fallback, which is capped too.
            raise zlib.error("incomplete or truncated stream")
        return out

    @staticmethod
    def decompressobj(*args: Any, **kwargs: Any) -> Any:
        budget = _budget.get()
        if budget is None or args or kwargs:
            return zlib.decompressobj(*args, **kwargs)
        return _CappedDecompressObj(budget)


_original_lzwdecode = pdftypes.lzwdecode
_original_rldecode = pdftypes.rldecode


def _capped_lzwdecode(data: bytes) -> bytes:
    budget = _budget.get()
    if budget is None:
        return _original_lzwdecode(data)
    chunks: list[bytes] = []
    for chunk in LZWDecoder(BytesIO(data)).run():
        budget.take(len(chunk))
        chunks.append(chunk)
    return b"".join(chunks)


def _capped_rldecode(data: bytes) -> bytes:
    """RunLengthDecode (PDF 1.7, 7.4.5), counting output against the budget."""
    budget = _budget.get()
    if budget is None:
        return _original_rldecode(data)
    out = bytearray()
    i = 0
    while i < len(data):
        length = data[i]
        if length == 128:  # end of data
            break
        if length < 128:
            run = data[i + 1 : i + 2 + length]
            i += 2 + length
        else:
            run = data[i + 1 : i + 2] * (257 - length)
            i += 2
        budget.take(len(run))
        out += run
    return bytes(out)


def install() -> None:
    """Point pdfminer's stream decoding at the capped decoders. Idempotent."""
    pdftypes.zlib = _CappedZlib  # type: ignore[assignment]
    pdftypes.lzwdecode = _capped_lzwdecode
    pdftypes.rldecode = _capped_rldecode
