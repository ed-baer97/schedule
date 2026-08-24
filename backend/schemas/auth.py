"""Auth API schemas."""
from pydantic import BaseModel, EmailStr, Field


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    school_id: int | None
    school_name: str | None = None

    model_config = {"from_attributes": True}
