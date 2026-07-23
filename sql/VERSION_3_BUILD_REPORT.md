# Version 3 build report

## Completed

- Added idempotent repairs for migrations 002 and 003.
- Retained Version 2 stabilization migration 004.
- Included password reset migration 005.
- Added Version 3 operational schema migration 006.
- Added a startup schema guard and removed startup `create_all` / runtime schema migration execution from `main.py`.
- Preserved protected SuperUser controls for `wjm@martinsdirect.com`.
- Preserved the single manager endpoint and single employee endpoint for all employee roles.
- Preserved manager/franchise commission visibility, participant calculations and notifications.
- Preserved password reset, show-password, additional-office and mobile Done navigation changes.
- Added Version 3 architecture and Render deployment documentation.
- Added Version 3 static regression verification.

## Verification performed

- Python compilation: passed.
- Existing workflow suite: 22 checks passed.
- Version 2 suite: 72 checks passed.
- Version 3 suite: 79 checks passed.

## Deployment validation still required

The build was not connected to the live Render PostgreSQL instance in this execution environment. After deployment, run Alembic and the included database audit against Render before accepting production traffic.
