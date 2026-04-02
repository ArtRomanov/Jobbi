from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    desired_role: str | None = None
    desired_location: str | None = None
    remote_preference: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = Field(default=None, max_length=3)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
