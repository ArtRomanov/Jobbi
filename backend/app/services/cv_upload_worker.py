"""Short-lived worker process for CV text extraction.

Run as ``python -m app.services.cv_upload_worker`` by
``cv_upload.extract_cv_text_async``: reads the file's bytes on stdin, writes
one JSON object on stdout, either ``{"text": ..., "truncated": ...}`` or
``{"error": <API error code>}``, and exits 0. A crash, a memory error or a
kill by the parent's timeout shows up as a non-zero exit or missing output.

Before reading the file it caps its own address space (``RLIMIT_AS``) where
the OS enforces it (Linux); on macOS the call is not enforced or refused, and
the decode cap in ``cv_upload`` plus the parent's timeout still apply.
"""

import json
import sys

import structlog

MEMORY_LIMIT_BYTES = 512 * 1024 * 1024


def _limit_memory() -> None:
    try:
        import resource
    except ImportError:  # not on POSIX
        return
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (ValueError, OSError):
        pass  # not supported here (macOS may refuse it)


def main() -> int:
    # Logs go to stderr: stdout carries only the result.
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(sys.stderr))
    _limit_memory()

    from app.services.cv_upload import CvUploadError, extract_text_only

    data = sys.stdin.buffer.read()
    try:
        text, truncated = extract_text_only(data)
        result: dict[str, object] = {"text": text, "truncated": truncated}
    except CvUploadError as exc:
        result = {"error": exc.code}
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
