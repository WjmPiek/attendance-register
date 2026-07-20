# Franchise Scope Fix Patch

This fixes the problem where a FranchiseUser can still see all system data.

It adds strict franchise scoping for:
- Attendance history
- Attendance approval list
- Franchise staff managers/employees
- Franchise staff creation
- Employee attendance owned by a franchise

It also includes a frontend page for creating managers and employees.

## Apply steps

1. Run SQL in DBeaver:

   sql/franchise_scope_fix.sql

2. Replace/copy backend files:
   - backend/app/api/attendance.py
   - backend/app/api/attendance_approval.py
   - backend/app/api/franchise_staff.py

3. Copy frontend file:
   - frontend/src/pages/FranchiseStaffPage.jsx

4. Register routers if not already registered in backend/app/api/routes.py:

```python
from app.api import franchise_staff
api_router.include_router(franchise_staff.router, prefix="/franchise-staff", tags=["franchise-staff"])
```

If your attendance approval router has a different name, keep your existing import, but replace the file contents.

5. Add a frontend navigation/card link to `FranchiseStaffPage` for FranchiseUser.

6. Restart backend and frontend:

```bash
uvicorn app.main:app --reload
npm run dev
```

## Important rule

FranchiseUser must only see:
- managers under their `franchise_users.id`
- employees under their `franchise_users.id`
- attendance events where the employee belongs to their franchise

ManagerUser must only see:
- employees assigned to that manager
- attendance events for those employees

EmployeeUser must only see:
- own attendance
