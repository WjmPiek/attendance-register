from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class Permission(Base, TimestampMixin):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship()


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))

    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship()


class SuperUser(Base, TimestampMixin):
    __tablename__ = "super_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FranchiseUser(Base, TimestampMixin):
    __tablename__ = "franchise_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    franchise_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    trading_as: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_registration_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    office_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    office_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    twenty_four_hour_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ManagerUser(Base, TimestampMixin):
    __tablename__ = "manager_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"), nullable=False)
    manager_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    employee_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    surname: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    office_address_assigned: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_start_time: Mapped[Optional[str]] = mapped_column(String(5), default="08:00")
    work_end_time: Mapped[Optional[str]] = mapped_column(String(5), default="17:00")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class EmployeeUser(Base, TimestampMixin):
    __tablename__ = "employee_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"), nullable=False)
    manager_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manager_users.id"), nullable=True)
    employee_role: Mapped[str] = mapped_column(String(80), default="Employee")
    id_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    employee_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    surname: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    office_address_assigned: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    work_start_time: Mapped[Optional[str]] = mapped_column(String(5), default="08:00")
    work_end_time: Mapped[Optional[str]] = mapped_column(String(5), default="17:00")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Area(Base, TimestampMixin):
    __tablename__ = "areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    allowed_radius_m: Mapped[int] = mapped_column(Integer, default=100)


class GPSAllocationPerUser(Base, TimestampMixin):
    __tablename__ = "gps_allocations_per_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    area_id: Mapped[Optional[int]] = mapped_column(ForeignKey("areas.id"), nullable=True)
    latitude: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    longitude: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    radius_meters: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserSuperUserAccess(Base, TimestampMixin):
    __tablename__ = "user_superuser_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    granter_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class UserFranchiseAccess(Base, TimestampMixin):
    __tablename__ = "user_franchise_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"))


class UserManagerAccess(Base, TimestampMixin):
    __tablename__ = "user_manager_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    manager_user_id: Mapped[int] = mapped_column(ForeignKey("manager_users.id"))


class UserEmployeeAccess(Base, TimestampMixin):
    __tablename__ = "user_employee_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    employee_user_id: Mapped[int] = mapped_column(ForeignKey("employee_users.id"))


class TimeRegistrarRule(Base, TimestampMixin):
    __tablename__ = "time_registrar_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    late_after_minutes: Mapped[int] = mapped_column(Integer, default=10)
    early_leave_before_minutes: Mapped[int] = mapped_column(Integer, default=10)
    allow_manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class GPSRule(Base, TimestampMixin):
    __tablename__ = "gps_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    require_gps_on_clock_in: Mapped[bool] = mapped_column(Boolean, default=True)
    require_gps_on_clock_out: Mapped[bool] = mapped_column(Boolean, default=True)
    allowed_radius_meters: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SignatureBlock(Base, TimestampMixin):
    __tablename__ = "signature_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class MonthlyMetric(Base, TimestampMixin):
    __tablename__ = "monthly_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    metric_month: Mapped[date] = mapped_column(Date)
    total_days_present: Mapped[int] = mapped_column(Integer, default=0)
    late_count: Mapped[int] = mapped_column(Integer, default=0)
    absent_count: Mapped[int] = mapped_column(Integer, default=0)
    attendance_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)


class Import(Base, TimestampMixin):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    imported_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)


class ImportRow(Base, TimestampMixin):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("imports.id", ondelete="CASCADE"))
    row_number: Mapped[int] = mapped_column(Integer)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ExportPDF(Base, TimestampMixin):
    __tablename__ = "export_pdfs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")


class AttendanceEvent(Base, TimestampMixin):
    __tablename__ = "attendance_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(20))

    latitude: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    longitude: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    accuracy_meters: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    device_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_image: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    signature_image_mime: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    signature_image_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attendance_photo: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    attendance_photo_mime: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    attendance_photo_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    photo_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="mobile")

    # NEW FIELDS
    distance_from_site_m: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    gps_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)

    left_early: Mapped[bool] = mapped_column(Boolean, default=False)
    early_leave_minutes: Mapped[int] = mapped_column(Integer, default=0)

    missing_sign_out: Mapped[bool] = mapped_column(Boolean, default=False)

    attendance_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Approval workflow fields
    approval_status: Mapped[str] = mapped_column(String(30), default="pending")
    work_location_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    employee_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manager_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_required: Mapped[bool] = mapped_column(Boolean, default=True)
    signature_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    qr_area_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    qr_office_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    qr_token_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class FranchiseRegistration(Base, TimestampMixin):
    __tablename__ = "franchise_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    business_name: Mapped[str] = mapped_column(String(255))
    trading_as: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_registration_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    vat_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    office_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    office_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    twenty_four_hour_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    franchisee_name: Mapped[str] = mapped_column(String(120))
    franchisee_surname: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    contact_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="pending")
    approved_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Allocation(Base, TimestampMixin):
    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    area_id: Mapped[Optional[int]] = mapped_column(ForeignKey("areas.id"), nullable=True)
    time_registrar_rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("time_registrar_rules.id"), nullable=True)
    gps_rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("gps_rules.id"), nullable=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    franchise_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    old_values: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_values: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_ip: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
