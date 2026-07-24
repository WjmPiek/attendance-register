from typing import List, Optional
from pydantic import BaseModel, EmailStr


class UserListItem(BaseModel):
    id: int
    full_name: str
    email: Optional[EmailStr] = None
    is_active: bool
    roles: List[str]


class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    roles: List[str] = []
