from fastapi import APIRouter, Depends

from app.api.deps import require_roles

router = APIRouter()


@router.get("/core-entities")
def core_entities(_=Depends(require_roles("SuperUser", "FranchiseUser", "ManagerUser", "EmployeeUser"))):
    return {
        "entities": [
            "users",
            "roles",
            "permissions",
            "role_permissions",
            "user_roles",
            "super_users",
            "franchise_users",
            "manager_users",
            "employee_users",
            "gps_allocations_per_user",
            "areas",
            "user_superuser_access",
            "user_franchise_access",
            "user_manager_access",
            "user_employee_access",
            "time_registrar_rules",
            "gps_rules",
            "signature_blocks",
            "monthly_metrics",
            "imports",
            "import_rows",
            "export_pdfs",
            "allocations",
        ]
    }
