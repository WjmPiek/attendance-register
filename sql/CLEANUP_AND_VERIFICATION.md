# Cleanup and workflow verification

This baseline centralizes browser authentication in `frontend/src/api/authSession.js`. Every API request now uses the same token source and a 401 response clears the stale token once, returning the user to login instead of showing repeated `Invalid token` messages.

Removed obsolete duplicate/temp source files:
- `backend/app/api/alerts.py.tmp.base`
- `backend/app/services/schema_migrations.py.tmp`
- `frontend/src/pages/franchise_staff.py`

Supported account roles:
- FranchiseUser: franchise administration and business information
- ManagerUser: manager self-service and assigned staff visibility
- EmployeeUser: employee self-service
- Agent: stored as an EmployeeUser with `employee_role = Agent`

Run verification:

```bash
python scripts/verify_workflow.py
python -m compileall backend/app
cd frontend && npm run build
```

A changed JWT secret invalidates old browser sessions. Users must sign in again, but no database migration is required solely for an `Invalid token` response.
