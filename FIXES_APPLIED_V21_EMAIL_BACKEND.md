# V21 Email backend fix

- Added central SMTP service with robust `.env` loading from backend/.env, project .env, or process environment.
- Gmail App Password whitespace is normalized automatically.
- Added safe email config diagnostics: `GET /api/alerts/email-config`.
- Rebuilt test endpoint: `POST /api/alerts/email-test`.
- Added retry endpoint: `POST /api/alerts/email-retry-pending`.
- Notifications now show `sent`, `failed`, or `pending` with `error_message`.
- No startup migration added.

Run backend from the backend folder:

```powershell
cd "D:\\ATTENDANCE REGISTAR\\attendance_register\\backend"
uvicorn app.main:app --reload
```

Test in FastAPI docs:

- `GET /api/alerts/email-config`
- `POST /api/alerts/email-test`
- `POST /api/alerts/email-retry-pending`

Security note: if an SMTP password was shared in chat or screenshots, revoke it and generate a new Gmail App Password.
