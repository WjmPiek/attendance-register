from fastapi import APIRouter

from app.api import (
    alerts,
    attendance,
    audit,
    auth,
    commission,
    franchise,
    franchise_dashboard,
    franchise_staff,
    irp5,
    leave,
    meta,
    payroll,
    roles,
    user_management,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(user_management.router, prefix="/users", tags=["user-management"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
api_router.include_router(franchise.router, prefix="/franchise", tags=["franchise"])
api_router.include_router(franchise_dashboard.router, prefix="/franchise", tags=["franchise-dashboard"])
api_router.include_router(franchise_staff.router, prefix="/franchise-staff", tags=["franchise-staff"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(commission.router, prefix="/commission", tags=["commission"])
api_router.include_router(irp5.router, prefix="/irp5", tags=["irp5"])
api_router.include_router(leave.router, prefix="/leave", tags=["leave"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["payroll"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
