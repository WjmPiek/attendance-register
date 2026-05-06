# Attendance Register Platform (Minimum Viable Structure)

This repository is a **minimum platform** that proves the structure for an attendance register product.
It includes:

- **GitHub-ready monorepo**
- **Backend app** (FastAPI)
- **Frontend app** (React + Vite)
- **PostgreSQL database**
- **Authentication** (JWT)
- **Roles and permissions**
- **Core entities and tables** aligned to your requested structure

## Repo structure

```text
attendance-register-platform/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   └── pages/
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.js
├── sql/
│   └── init.sql
├── docker-compose.yml
├── docs/ERD.md
└── README.md
```

## Architecture

### Backend
- FastAPI
- SQLAlchemy ORM
- JWT authentication
- RBAC authorization hooks
- PostgreSQL persistence

### Frontend
- React + Vite
- login screen
- dashboard for current user context
- placeholder views proving entity structure

### Database
Core tables included in code/schema:

- users
- roles
- permissions
- role_permissions
- user_roles
- super_users
- franchise_users
- manager_users
- employee_users
- gps_allocations_per_user
- areas
- user_superuser_access
- user_franchise_access
- user_manager_access
- user_employee_access
- time_registrar_rules
- gps_rules
- signature_blocks
- monthly_metrics
- imports
- import_rows
- export_pdfs
- allocations

## Quick start

### Option 1: Docker Compose

```bash
docker compose up --build
```

Services:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432

### Option 2: Run locally

#### Database
Start PostgreSQL and create a database named `attendance_register`.

#### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Seeded login
The app auto-seeds a default SuperUser on backend startup.

- Email: `admin@example.com`
- Password: `Admin123!`

## Example API flow

1. `POST /api/auth/login`
2. copy access token
3. use `Authorize` in `/docs`
4. call:
   - `GET /api/auth/me`
   - `GET /api/users`
   - `GET /api/roles`
   - `GET /api/meta/core-entities`

## What is intentionally minimal
This is a proof-of-structure, not a fully completed enterprise system.
Included:
- working auth
- working RBAC foundations
- full schema structure
- seed data
- example protected APIs
- simple frontend

Not fully implemented yet:
- biometric/signature capture
- GPS boundary validation engine
- import/export processing jobs
- PDF generation pipeline
- attendance event engine
- audit trail and approvals workflow
- complete CRUD for every table

## Recommended next steps
1. Add migrations with Alembic.
2. Add attendance_events / shifts / schedules tables.
3. Complete CRUD per entity.
4. Add permission-aware menus and route guards in frontend.
5. Add import processing workers and PDF export service.
6. Add automated tests and CI.

## Suggested GitHub repo name
`attendance-register-platform`

## Suggested initial commit message
`feat: scaffold minimum attendance register platform with auth rbac frontend backend and postgres`


## ERD
See `docs/ERD.md` for a lightweight entity-relationship view.


## Mobile employee sign-in/sign-out

This proof-of-structure repo now includes a minimal employee mobile attendance flow.

### Included
- mobile-friendly frontend screen for employees
- backend attendance endpoints
- GPS capture from the browser
- device info capture
- signature marker field
- attendance_events table

### Demo employee login
- `employee@example.com`
- `Employee123!`

### API
- `GET /api/attendance/status`
- `POST /api/attendance/sign-in`
- `POST /api/attendance/sign-out`
