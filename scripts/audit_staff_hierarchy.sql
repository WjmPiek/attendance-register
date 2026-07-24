-- Phase 1 read-only production audit.
-- A healthy result returns zero rows from every section.

-- Staff profiles without a valid user, franchise, or expected role.
SELECT 'manager_integrity' AS issue, mu.id AS staff_id, mu.user_id, mu.franchise_user_id
FROM manager_users mu
LEFT JOIN users u ON u.id = mu.user_id
LEFT JOIN franchise_users fu ON fu.id = mu.franchise_user_id
WHERE u.id IS NULL
   OR fu.id IS NULL
   OR NOT EXISTS (
       SELECT 1
       FROM user_roles ur
       JOIN roles r ON r.id = ur.role_id
       WHERE ur.user_id = mu.user_id AND r.name = 'ManagerUser'
   );

SELECT 'employee_integrity' AS issue, eu.id AS staff_id, eu.user_id, eu.franchise_user_id
FROM employee_users eu
LEFT JOIN users u ON u.id = eu.user_id
LEFT JOIN franchise_users fu ON fu.id = eu.franchise_user_id
WHERE u.id IS NULL
   OR fu.id IS NULL
   OR NOT EXISTS (
       SELECT 1
       FROM user_roles ur
       JOIN roles r ON r.id = ur.role_id
       WHERE ur.user_id = eu.user_id AND r.name = 'EmployeeUser'
   );

-- Employees assigned to a manager owned by another franchise.
SELECT
    'cross_franchise_manager' AS issue,
    eu.id AS employee_id,
    eu.franchise_user_id AS employee_franchise_id,
    eu.manager_user_id,
    mu.franchise_user_id AS manager_franchise_id
FROM employee_users eu
JOIN manager_users mu ON mu.id = eu.manager_user_id
WHERE eu.franchise_user_id <> mu.franchise_user_id;

-- Active staff without exactly one active office in their franchise.
WITH staff AS (
    SELECT 'manager' AS staff_type, id AS staff_id, user_id, franchise_user_id
    FROM manager_users WHERE COALESCE(is_active, TRUE) = TRUE
    UNION ALL
    SELECT 'employee', id, user_id, franchise_user_id
    FROM employee_users WHERE COALESCE(is_active, TRUE) = TRUE
)
SELECT
    'office_assignment' AS issue,
    s.staff_type,
    s.staff_id,
    s.user_id,
    COUNT(g.id) AS active_office_count
FROM staff s
LEFT JOIN gps_allocations_per_user g
    ON g.user_id = s.user_id AND COALESCE(g.is_active, TRUE) = TRUE
LEFT JOIN areas a
    ON a.id = g.area_id
   AND a.franchise_user_id = s.franchise_user_id
   AND COALESCE(a.is_archived, FALSE) = FALSE
GROUP BY s.staff_type, s.staff_id, s.user_id
HAVING COUNT(a.id) <> 1;

-- A person must not have both manager and employee profiles.
SELECT
    'duplicate_staff_profile' AS issue,
    mu.user_id,
    mu.id AS manager_id,
    eu.id AS employee_id
FROM manager_users mu
JOIN employee_users eu ON eu.user_id = mu.user_id;

-- Staff accounts must have exactly one organisational role.
SELECT
    'organisational_role_count' AS issue,
    u.id AS user_id,
    COUNT(*) AS role_count,
    STRING_AGG(r.name, ', ' ORDER BY r.name) AS roles
FROM users u
JOIN user_roles ur ON ur.user_id = u.id
JOIN roles r ON r.id = ur.role_id
WHERE EXISTS (SELECT 1 FROM manager_users mu WHERE mu.user_id = u.id)
   OR EXISTS (SELECT 1 FROM employee_users eu WHERE eu.user_id = u.id)
GROUP BY u.id
HAVING COUNT(*) <> 1;
