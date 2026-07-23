from fastapi import APIRouter

from app.api import auth, users, roles, meta, attendance, franchise, franchise_staff, franchise_dashboard, user_management

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
