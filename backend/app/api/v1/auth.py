from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import create_access_token
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.schemas.user import UserRead
from app.services.auth_service import authenticate_user, create_user, get_user_by_email
from app.services.password_reset_service import (
    create_password_reset,
    verify_and_use_reset_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    existing = await get_user_by_email(db, body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )

    user = await create_user(db, body)
    token = create_access_token(subject=user.id)

    return AuthResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    token = create_access_token(subject=user.id)

    return AuthResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    # Always return the same response regardless of whether the email exists
    user = await get_user_by_email(db, body.email)
    if user is not None:
        await create_password_reset(db, user)

    return {
        "message": "If an account with that email exists, we've sent a password reset link."
    }


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    success = await verify_and_use_reset_token(db, body.token, body.new_password)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link has expired. Please request a new one.",
        )

    return {"message": "Password reset successfully."}


@router.post("/logout")
async def logout() -> dict[str, str]:
    # Client-side token clearing handles the actual logout.
    # This endpoint exists for future server-side token invalidation.
    return {"message": "Logged out."}
