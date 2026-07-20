# V24 CORS Localhost Fix

Fixed frontend fetch failures from `http://localhost:5173` to `http://127.0.0.1:8000`.

Changes:
- Made FastAPI CORS development config permissive for local/LAN testing.
- Added catch-all OPTIONS preflight handler.
- Kept favicon 204 response.

After applying, restart backend:

```powershell
cd backend
uvicorn app.main:app --reload
```

Then hard refresh the browser.
