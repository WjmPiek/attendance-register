from typing import List
from pydantic import BaseModel


class RoleListItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    permissions: List[str]
