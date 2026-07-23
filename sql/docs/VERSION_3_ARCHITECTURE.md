# Attendance Register Version 3

Version 3 is a layered stabilization release built on the Version 2 data model.

## Layers

1. **Alembic-owned schema** – operational tables are created by migrations, not by user requests.
2. **Identity and tenancy** – every manager and employee is linked to one franchise; employees may additionally link to one manager.
3. **Protected platform owner** – `wjm@martinsdirect.com` is the immutable SuperUser account.
4. **Staff workflow** – managers and all employee roles use the same user/profile creation contract.
5. **Commission workflow** – managers and employees are participants; manager/franchise review and notifications share one path.
6. **Attendance workflow** – desktop, mobile and QR events write to the same attendance event table.
7. **Business offices** – multiple active offices per franchise, archival instead of destructive deletion.
8. **Documents** – payroll and IRP5 documents are franchise-scoped and user-scoped.
9. **Notifications and email** – in-app notifications and SMTP reset links are separate delivery channels.
10. **Verification** – static workflow verification, model/schema audit and Alembic history checks ship with the build.

## Deployment invariant

Render must run `python -m alembic upgrade head` before starting Uvicorn. The expected head is `006_v3_operational_schema`.
