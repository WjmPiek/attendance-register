# Martins Attendance - Login and Password Reset Fixes

Included fixes:

- Removed the extra `Login` heading above the logo on the login card.
- Re-spaced the login card so the logo, email, password, forgot password, and franchise registration areas flow correctly.
- Added working public `Forgot password?` lookup endpoint.
- Added FranchiseUser/SuperUser staff password reset endpoints:
  - `POST /api/franchise-staff/managers/{manager_id}/reset-password`
  - `POST /api/franchise-staff/employees/{employee_id}/reset-password`
- Added `Reset Password` action links next to Manager and Employee records in HR Staff.
- Password reset keeps staff records in the franchise scope, so a FranchiseUser can only reset passwords for their own managers/employees.

How to use password reset:

1. Login as the FranchiseUser.
2. Open **HR Staff**.
3. Find the manager or employee.
4. Click **Reset Password**.
5. Enter a new password with at least 8 characters.
6. The staff member can login with that new password.

Forgot password behavior:

- Manager/employee enters their email on the login page and clicks **Forgot password?**.
- The app tells them that their FranchiseUser can reset it from HR Staff.
- The local/offline build does not send email automatically.
