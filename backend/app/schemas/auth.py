from typing import List, Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    # Accept either an email address or a username in the same login field.
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: int
    full_name: str
    email: Optional[str] = None
    username: Optional[str] = None
    roles: List[str]
    employee_role: Optional[str] = None
    franchise_user_id: Optional[int] = None
