from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class FranchiseRegistrationCreate(BaseModel):
    business_name: str = Field(..., min_length=2)
    trading_as: Optional[str] = None
    business_registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    office_address: Optional[str] = None
    website: Optional[str] = None
    office_number: Optional[str] = None
    twenty_four_hour_number: Optional[str] = None

    franchisee_name: str = Field(..., min_length=2)
    franchisee_surname: str = Field(..., min_length=2)
    email: EmailStr
    contact_number: Optional[str] = None

    password: str = Field(..., min_length=8)


class FranchiseRegistrationResponse(BaseModel):
    id: int
    business_name: str
    trading_as: Optional[str] = None
    business_registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    office_address: Optional[str] = None
    website: Optional[str] = None
    office_number: Optional[str] = None
    twenty_four_hour_number: Optional[str] = None
    franchisee_name: str
    franchisee_surname: str
    email: EmailStr
    contact_number: Optional[str] = None
    status: str
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FranchiseRegistrationDecision(BaseModel):
    note: Optional[str] = None


class FranchiseRegistrationUpdate(BaseModel):
    business_name: Optional[str] = None
    trading_as: Optional[str] = None
    business_registration_number: Optional[str] = None
    vat_number: Optional[str] = None
    office_address: Optional[str] = None
    website: Optional[str] = None
    office_number: Optional[str] = None
    twenty_four_hour_number: Optional[str] = None
    franchisee_name: Optional[str] = None
    franchisee_surname: Optional[str] = None
    email: Optional[EmailStr] = None
    contact_number: Optional[str] = None

class FranchiseUpdate(BaseModel):
    business_name: str
    trading_as: str
    business_registration: str
    vat_nr: Optional[str] = None
    office_address: str
    website: Optional[str] = None   # 🔥 MUST EXIST
    office_number: Optional[str] = None
    contact: Optional[str] = None