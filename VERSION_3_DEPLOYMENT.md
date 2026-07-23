# Version 3 Render deployment

Backend root: `backend`

Build command:

```bash
pip install -r requirements.txt && python -m alembic upgrade head
```

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

After deployment:

```bash
cd /opt/render/project/src/backend
python -m alembic current
PYTHONPATH=. python ../scripts/database_audit.py
PYTHONPATH=. python ../scripts/verify_v3.py
```

Expected Alembic head: `006_v3_operational_schema`.
