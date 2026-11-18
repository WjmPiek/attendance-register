"""Requisition records and evidence live in PostgreSQL, not ephemeral uploads."""

from datetime import date, datetime
from sqlalchemy import (
    Integer,
    Boolean,
    BigInteger,
    String,
    Text,
    Date,
    DateTime,
    LargeBinary,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class RequisitionGrant(Base):
    __tablename__ = "requisition_grants"
    __table_args__ = (UniqueConstraint("franchise_user_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class RequisitionSource(Base):
    __tablename__ = "requisition_sources"
    __table_args__ = (UniqueConstraint("franchise_user_id", "sha256"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"))
    sha256: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class RequisitionBook(Base):
    __tablename__ = "requisition_books"
    __table_args__ = (UniqueConstraint("branch_id", "reference"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"))
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    reference: Mapped[str] = mapped_column(String(255))
    deceased: Mapped[str] = mapped_column(String(255))
    details: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("requisition_sources.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class RequisitionMonth(Base):
    __tablename__ = "requisition_months"
    __table_args__ = (UniqueConstraint("branch_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    franchise_user_id: Mapped[int] = mapped_column(ForeignKey("franchise_users.id"))
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[str] = mapped_column(String(7))
    holder: Mapped[str] = mapped_column(String(255))
    opening_cents: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="open")
    closing_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Requisition(Base):
    __tablename__ = "requisitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(
        ForeignKey("requisition_months.id"), index=True
    )
    book_id: Mapped[int] = mapped_column(ForeignKey("requisition_books.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    employee_name: Mapped[str] = mapped_column(String(255))
    request_date: Mapped[date] = mapped_column(Date)
    number: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[str] = mapped_column(Text, default="{}")
    lines: Mapped[str] = mapped_column(Text, default="[]")
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RequisitionRevision(Base):
    __tablename__ = "requisition_revisions"
    __table_args__ = (UniqueConstraint("requisition_id", "revision"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    requisition_id: Mapped[int] = mapped_column(ForeignKey("requisitions.id"))
    revision: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    snapshot: Mapped[str] = mapped_column(Text)


class RequisitionTransaction(Base):
    __tablename__ = "requisition_transactions"
    __table_args__ = (UniqueConstraint("month_id", "client_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(
        ForeignKey("requisition_months.id"), index=True
    )
    requisition_id: Mapped[int] = mapped_column(ForeignKey("requisitions.id"))
    client_key: Mapped[str] = mapped_column(String(36))
    transaction_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))
    supplier: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(1000))
    amount_cents: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    actor_name: Mapped[str] = mapped_column(String(255))
    receipt_name: Mapped[str] = mapped_column(String(255))
    receipt_mime: Mapped[str] = mapped_column(String(80))
    receipt_content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class RequisitionEmail(Base):
    __tablename__ = "requisition_emails"
    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("requisition_months.id"))
    subject: Mapped[str] = mapped_column(String(500))
    message: Mapped[str] = mapped_column(Text)
    workbook: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    document: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recipient: Mapped[str] = mapped_column(String(255), default="wjm@martinsdirect.com")
    include_workbook: Mapped[bool] = mapped_column(Boolean, default=True)


class RequisitionReportSetting(Base):
    __tablename__ = "requisition_report_settings"
    franchise_user_id: Mapped[int] = mapped_column(
        ForeignKey("franchise_users.id"), primary_key=True
    )
    recipient: Mapped[str] = mapped_column(String(255), default="wjm@martinsdirect.com")


class RequisitionMonthlyReport(Base):
    __tablename__ = "requisition_monthly_reports"
    month_id: Mapped[int] = mapped_column(
        ForeignKey("requisition_months.id"), primary_key=True
    )
    email_id: Mapped[int] = mapped_column(ForeignKey("requisition_emails.id"))


TABLES = [
    RequisitionGrant.__table__,
    RequisitionSource.__table__,
    RequisitionBook.__table__,
    RequisitionMonth.__table__,
    Requisition.__table__,
    RequisitionRevision.__table__,
    RequisitionTransaction.__table__,
    RequisitionEmail.__table__,
    RequisitionReportSetting.__table__,
    RequisitionMonthlyReport.__table__,
]
