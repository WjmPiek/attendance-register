-- Clears existing managers, employees, and their operational records.
-- Keeps SuperUser accounts, franchise users, franchise registrations, roles, and offices.
-- Run manually against the target PostgreSQL database when you want to start staff capture again.

BEGIN;

CREATE TEMP TABLE removed_staff_users AS
SELECT user_id FROM manager_users
UNION
SELECT user_id FROM employee_users;

TRUNCATE TABLE
    manager_users,
    employee_users
RESTART IDENTITY CASCADE;

DELETE FROM gps_allocations_per_user
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM allocations
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM signature_blocks
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM monthly_metrics
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM attendance_events
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM notifications
WHERE user_id IN (SELECT user_id FROM removed_staff_users)
   OR recipient_user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM leave_applications
WHERE applicant_user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM commission_entries
WHERE employee_user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM payroll_payslips
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM irp5_documents
WHERE target_user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM user_roles
WHERE user_id IN (SELECT user_id FROM removed_staff_users);

DELETE FROM users
WHERE id IN (SELECT user_id FROM removed_staff_users);

DROP TABLE removed_staff_users;

COMMIT;
