from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, users, roles, meta, attendance, franchise, franchise_staff, franchise_dashboard, user_management, alerts, irp5, leave, payroll, audit, commission
from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine
from app.services.seed import seed_initial_data
from app.services.schema_migrations import ensure_runtime_schema


app = FastAPI(title="Attendance Register Platform API", version="0.1.0")

# CORS for local Vite/frontend during development and LAN testing.
# This intentionally allows localhost/127.0.0.1 on any port, so the frontend
# can call http://127.0.0.1:8000 from http://localhost:5173 without being blocked.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=r"https?://.*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)


def _cors_headers_for_request(request: Request) -> dict:
    origin = request.headers.get("origin") or "*"
    return {
        "Access-Control-Allow-Origin": origin if origin != "null" else "*",
        "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": request.headers.get("access-control-request-headers", "Authorization,Content-Type"),
        "Access-Control-Expose-Headers": "Content-Disposition,Content-Type",
        "Vary": "Origin",
    }


@app.middleware("http")
async def cors_and_error_safety_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_cors_headers_for_request(request))
    try:
        response = await call_next(request)
    except Exception as exc:
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)})
    for key, value in _cors_headers_for_request(request).items():
        response.headers.setdefault(key, value)
    return response


@app.options("/{full_path:path}", include_in_schema=False)
def cors_preflight(full_path: str):
    return Response(status_code=204)


@app.get("/")
def api_root():
    return {
        "status": "running",
        "app": "Attendance Register Platform API",
        "docs": "/docs",
        "health": "/health",
        "login_endpoint": "/api/auth/login",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/health")
def api_health_check():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    seed_initial_data()


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(roles.router, prefix="/api/roles", tags=["roles"])
app.include_router(meta.router, prefix="/api/meta", tags=["meta"])
app.include_router(attendance.router, prefix="/api/attendance", tags=["attendance"])
app.include_router(franchise.router, prefix="/api/franchise", tags=["franchise"])
app.include_router(franchise_dashboard.router, prefix="/api/franchise", tags=["franchise-dashboard"])
app.include_router(franchise_staff.router, prefix="/api/franchise-staff", tags=["franchise-staff"])
app.include_router(user_management.router, prefix="/api/users", tags=["user-management"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts-notifications"])

app.include_router(irp5.router, prefix="/api/irp5", tags=["irp5-documents"])

app.include_router(leave.router, prefix="/api/leave", tags=["leave-management"])
app.include_router(payroll.router, prefix="/api/payroll", tags=["payroll"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit-logs"])
app.include_router(commission.router, prefix="/api/commission", tags=["commission-overtime"])
