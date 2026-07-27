from app.main import app


def test_phase_subsystem_routes_are_registered():
    paths = {route.path for route in app.routes}

    expected_paths = {
        "/api/alerts/summary",
        "/api/commission/types",
        "/api/leave/applications",
        "/api/payroll/imports",
        "/api/irp5/documents",
        "/api/audit/logs",
        "/api/attendance/office-qr/offices",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
    }

    assert expected_paths <= paths
