# Office Hours on Staff Creation

Added office hours to the unified HR staff form.

## Included
- Office Start Time and Office End Time fields when creating or editing staff.
- Defaults: 08:00 to 17:00.
- Saves office hours for both managers and employees.
- Staff list now shows Office Hours.
- View/Edit actions include office hour details.
- Backend adds missing `work_start_time` and `work_end_time` columns automatically for existing databases.
- Attendance late and early-leave calculations now use the signed-in user's configured office hours instead of fixed 08:00/17:00.

## Database columns added automatically
- `manager_users.work_start_time`
- `manager_users.work_end_time`
- `employee_users.work_start_time`
- `employee_users.work_end_time`
