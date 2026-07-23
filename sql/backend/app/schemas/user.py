from typing import List
from pydantic import BaseModel, EmailStr


class UserListItem(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    is_active: bool
    roles: List[str]


class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    roles: List[str] = []
