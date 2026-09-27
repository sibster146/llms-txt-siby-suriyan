from pydantic import BaseModel, EmailStr, Field


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class UserResponse(BaseModel):
    user_id: str
    email: EmailStr
