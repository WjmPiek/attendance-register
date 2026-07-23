# Render database reset — preserve Martinsdirect SuperUser

This build includes a guarded one-time reset script. It deletes all franchise,
staff, attendance, commission, leave, payroll, IRP5, QR, business information,
notification, and other operational records. It preserves only:

- `wjm@martinsdirect.com`
- the SuperUser role and authorization reference data
- Alembic migration history

Run from the Render backend Shell:

```bash
cd /opt/render/project/src
CONFIRM_DATABASE_RESET=DELETE_ALL_EXCEPT_WJM PYTHONPATH=backend python scripts/reset_render_data_keep_superuser.py
```

Then verify:

```bash
cd /opt/render/project/src/backend
python -m alembic current
PYTHONPATH=. python ../scripts/database_audit.py
```

The application startup seed now creates only roles and permissions. It no longer
creates demo users, demo franchises, demo employees, or sample data.
