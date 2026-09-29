from pydantic import BaseModel, EmailStr, Field


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class UserResponse(BaseModel):
    user_id: str
    email: EmailStr


class GuestSessionResponse(BaseModel):
    user_id: str
    email: EmailStr
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
