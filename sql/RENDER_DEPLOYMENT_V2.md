# Attendance Register Version 2 - Render deployment

## Architecture
- Frontend: Render Static Site
- Backend API: Render Web Service
- Database: Render PostgreSQL
- All franchise data is stored centrally in Render PostgreSQL. A local PC is not required to remain powered on.

## Backend environment variables
Set these on the Render **backend Web Service**, not on the database page:

- `ENVIRONMENT=production`
- `DATABASE_URL` = the Render PostgreSQL **Internal Database URL**
- `JWT_SECRET_KEY` = a long stable random value; do not change it after users sign in
- `FRONTEND_URL` = the deployed frontend URL

Render also provides `RENDER=true`; Version 2 refuses to start if Render is configured with a localhost database URL.

## Build and start commands
Root directory: `backend`

Build command:

```bash
pip install -r requirements.txt && python -m alembic upgrade head
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## One-time database check in Render backend Shell

```bash
python -m alembic current
python -m alembic upgrade head
python ../scripts/database_audit.py
```

Expected migration head: `004_stabilization_v2`.
