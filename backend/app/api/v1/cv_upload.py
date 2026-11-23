"""``POST /api/v1/cvs/upload``: create an own CV from a PDF or DOCX file.

Size limits, in the order they apply:

1. ``Content-Length`` over ``MAX_UPLOAD_REQUEST_BYTES`` is rejected with 413
   before the multipart body is parsed (``_UploadSizeLimitRoute``). The limit
   is the 5 MB file cap plus ``MULTIPART_OVERHEAD_BYTES`` for the multipart
   framing (boundaries and part headers, including the file name), so a file
   just under 5 MB is never refused here.
2. The same limit is enforced on the bytes actually streamed in, which covers
   chunked requests that send no ``Content-Length``.
3. The handler reads at most ``MAX_UPLOAD_BYTES + 1`` bytes of the file and
   ``extract_cv_text`` raises ``FileTooLarge`` past 5 MB.

Our code never writes the file to disk. Starlette's multipart parser keeps
each file in a ``SpooledTemporaryFile``, which moves to a temp file once it
passes 1 MB; the temp file is deleted when the request ends.
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Message, Receive

from app.api.v1.cvs import cv_to_read
from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.cv import CvCreate, CvUploadRead
from app.services.cv_service import create_uploaded_cv
from app.services.cv_upload import (
    MAX_UPLOAD_BYTES,
    CvUploadError,
    FileTooLarge,
    NoText,
    UnsupportedFile,
    UploadFailed,
    extract_cv_text_async,
)

logger = structlog.get_logger()

# Multipart framing around the file: two boundary lines and the part headers
# (Content-Disposition with a file name of up to a few hundred bytes, plus
# Content-Type). 64 KiB is far more than any real client sends.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_UPLOAD_REQUEST_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES

_ERROR_STATUS: dict[type[CvUploadError], HTTPStatus] = {
    FileTooLarge: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    UnsupportedFile: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    NoText: HTTPStatus.UNPROCESSABLE_ENTITY,
    UploadFailed: HTTPStatus.BAD_REQUEST,
}


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail=FileTooLarge.code
    )


def _declared_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


def _capped_receive(receive: Receive, limit: int) -> Receive:
    """Wrap ``receive`` so a body longer than ``limit`` bytes stops with 413."""
    received = 0

    async def capped() -> Message:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                # FastAPI re-raises HTTPExceptions raised while reading the body.
                raise _too_large()
        return message

    return capped


class _UploadSizeLimitRoute(APIRoute):
    """Reject an oversized upload before FastAPI parses the multipart body."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handler = super().get_route_handler()

        async def size_limited_handler(request: Request) -> Response:
            declared = _declared_length(request)
            if declared is not None and declared > MAX_UPLOAD_REQUEST_BYTES:
                return JSONResponse(
                    status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": FileTooLarge.code},
                )
            capped = Request(
                request.scope,
                _capped_receive(request.receive, MAX_UPLOAD_REQUEST_BYTES),
            )
            return await handler(capped)

        return size_limited_handler


router = APIRouter(prefix="/cvs", tags=["cvs"], route_class=_UploadSizeLimitRoute)


def _error_doc(code: str, meaning: str) -> dict[str, object]:
    return {
        "description": f"`{code}`: {meaning}",
        "content": {"application/json": {"example": {"detail": code}}},
    }


@router.post(
    "/upload",
    response_model=CvUploadRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a CV from an uploaded PDF or DOCX",
    responses={
        400: _error_doc(UploadFailed.code, "the file could not be read"),
        413: _error_doc(FileTooLarge.code, "the file is larger than 5 MB"),
        415: _error_doc(UnsupportedFile.code, "the content is not a PDF or DOCX"),
        422: _error_doc(NoText.code, "the file holds no readable text"),
    },
)
async def upload_user_cv(
    file: Annotated[UploadFile, File(description="One PDF or DOCX file, up to 5 MB")],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CvUploadRead:
    try:
        # One byte over the cap is enough for extract_cv_text to refuse it.
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        extracted = await extract_cv_text_async(data, file.filename or "")
    except CvUploadError as exc:
        logger.info("cv_upload_rejected", code=exc.code)
        raise HTTPException(
            status_code=_ERROR_STATUS.get(type(exc), HTTPStatus.BAD_REQUEST),
            detail=exc.code,
        ) from exc
    # Broad on purpose: any other failure is UPLOAD_FAILED. Only the type is
    # logged, never the message, which could quote the file's content.
    except Exception as exc:
        logger.warning("cv_upload_failed", error_type=type(exc).__name__)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=UploadFailed.code
        ) from exc

    cv, became_base = await create_uploaded_cv(
        db, current_user.id, CvCreate(name=extracted.name, content=extracted.text)
    )
    logger.info(
        "cv_uploaded",
        cv_id=cv.id,
        truncated=extracted.truncated,
        became_base=became_base,
    )
    # Built from the same CvRead the other CV endpoints return, so new CvRead
    # fields show up here without changes.
    return CvUploadRead(
        **(await cv_to_read(db, current_user.id, cv)).model_dump(),
        became_base=became_base,
        truncated=extracted.truncated,
    )
