from typing import Optional

from pydantic import BaseModel


class AttendanceActionRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    accuracy_meters: Optional[float] = None
    device_info: Optional[str] = None
    signature_value: Optional[str] = None
    photo_value: Optional[str] = None
    work_location_type: Optional[str] = 'office'  # office or on_road
    employee_note: Optional[str] = None
    qr_value: Optional[str] = None


class AttendanceActionResponse(BaseModel):
    message: str
    action: str
    current_status: str


class AttendanceStatusResponse(BaseModel):
    current_status: str
    last_action: Optional[str] = None
    last_action_at: Optional[str] = None


class AttendanceHistoryItem(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    user_surname: Optional[str] = None
    user_full_name: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    user_staff_type: Optional[str] = None
    action: str
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    accuracy_meters: Optional[str] = None
    distance_from_site_m: Optional[float] = None
    gps_status: Optional[str] = None
    is_late: bool = False
    late_minutes: int = 0
    left_early: bool = False
    early_leave_minutes: int = 0
    missing_sign_out: bool = False
    attendance_status: Optional[str] = None
    approval_status: Optional[str] = 'pending'
    work_location_type: Optional[str] = None
    employee_note: Optional[str] = None
    manager_note: Optional[str] = None
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[str] = None
    rejected_reason: Optional[str] = None
    signature_status: Optional[str] = None
    photo_status: Optional[str] = None
    created_at: str
    map_url: Optional[str] = None


class AttendanceHistoryResponse(BaseModel):
    items: list[AttendanceHistoryItem]


class AttendanceSessionItem(BaseModel):
    session_id: str
    user_id: int
    user_name: Optional[str] = None
    user_surname: Optional[str] = None
    user_full_name: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    user_staff_type: Optional[str] = None
    sign_in_event_id: Optional[int] = None
    sign_out_event_id: Optional[int] = None
    sign_in_at: Optional[str] = None
    sign_out_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    status: str
    gps_status: Optional[str] = None
    approval_status: Optional[str] = 'pending'
    work_location_type: Optional[str] = None
    is_late: bool = False
    late_minutes: int = 0
    left_early: bool = False
    early_leave_minutes: int = 0
    missing_sign_out: bool = False
    sign_in_map_url: Optional[str] = None
    sign_out_map_url: Optional[str] = None


class AttendanceSessionSummary(BaseModel):
    total_sessions: int = 0
    completed_sessions: int = 0
    open_sessions: int = 0
    missing_sign_out: int = 0
    late_sessions: int = 0
    early_leave_sessions: int = 0
    outside_area: int = 0
    low_accuracy: int = 0
    pending_approval: int = 0
    approved: int = 0
    rejected: int = 0
    total_minutes: int = 0


class AttendanceSessionsResponse(BaseModel):
    items: list[AttendanceSessionItem]
    summary: AttendanceSessionSummary


class ApprovalDecisionRequest(BaseModel):
    manager_note: Optional[str] = None
    rejected_reason: Optional[str] = None


class ApprovalListResponse(BaseModel):
    items: list[AttendanceHistoryItem]

class ScanRequest(BaseModel):
    qr_code: str
    lat: float
    lng: float
