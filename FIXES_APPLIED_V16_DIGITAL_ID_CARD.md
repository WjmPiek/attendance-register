# V16 Digital Employee ID Card

Added a digital staff ID card to the employee mobile attendance page.

## Backend
- Added `GET /api/franchise-staff/id-card/me`.
- Returns the logged-in employee/manager/user card details.
- Includes linked ID photo from `employee_users`, `manager_users`, or `users`.
- Includes franchise, office, role, user ID and staff QR payload.
- No startup migration added.

## Frontend
- Added `DigitalIdCard` component.
- Displays on the Mobile Sign In page above the sign-in/out form.
- Shows uploaded ID photo, staff details, Martins logo, active status, and staff QR payload.
- Responsive for mobile use.

## Database
- Uses existing ID photo columns from v13/v14/v15.
- No new SQL required.
