# Phase 1 — Staff & Hierarchy

## Implemented

- [x] One atomic user/profile creation flow for managers and employees
- [x] Username is persisted and can be used to log in when email is absent
- [x] Legacy databases allow `users.email` to be NULL for username-only accounts
- [x] Active email and username collisions are rejected
- [x] Staff accounts receive exactly one expected role assignment
- [x] Generic user creation rejects roles that require organisational profiles
- [x] Franchise ownership is required for new manager and employee rows
- [x] Employee manager assignments are limited to the same franchise
- [x] Staff must be assigned to a registered, active franchise office
- [x] Franchise users see only their own managers and employees
- [x] Managers can open only their own profile and assigned employees
- [x] SuperUser can select a franchise and see/create staff in that scope
- [x] Partial edits preserve omitted identity, username, email, and password fields
- [x] Employee manager assignment can be explicitly cleared
- [x] Database migration protects franchise and manager ownership for new writes
- [x] Read-only SQL audit added for legacy production rows

## Local verification

- [x] Python source compilation
- [x] Staff hierarchy regression tests
- [x] FastAPI OpenAPI generation
- [x] Frontend JSX/TypeScript parsing
- [ ] Vite production build (blocked locally by sandbox `spawn EPERM`)

## Production verification required before Phase 2

- [ ] Run Alembic through `007_staff_hierarchy_integrity`
- [ ] Run `scripts/audit_staff_hierarchy.sql`; repair every returned legacy row
- [ ] Test Franchise → Manager → Employee creation with email
- [ ] Test Franchise → Manager → Employee creation with username only
- [ ] Test employee reassignment and removal of manager assignment
- [ ] Confirm Manager A cannot see Manager B's employees
- [ ] Confirm each franchise cannot see another franchise's staff
- [ ] Confirm SuperUser franchise selector scopes managers, employees, and offices
- [ ] Confirm an edit with blank password preserves the current password
- [ ] Confirm username, ID number, employee number, and email survive edits
