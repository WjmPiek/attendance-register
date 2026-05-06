# Fixes Applied V11

- Removed runtime schema migration call from `app/main.py` so backend startup no longer hangs at `Waiting for application startup`.
- Kept signature image storage request-safe: attendance endpoints still add required signature columns lazily when sign-in/out is used.
- Signature canvas data is saved as binary image data on attendance events and embedded into attendance PDF exports.
- Added franchise-linked notification outbox records for attendance sign-in/sign-out events.
- Notifications now store `user_id` (staff), `recipient_user_id` (franchise account), `franchise_user_id`, `recipient_email`, `target_tab`, and related attendance event id.
- Optional SMTP email sending is supported through env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`. Without SMTP config, notifications remain as pending outbox rows.

Run backend with your normal command:

```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\backend"
uvicorn app.main:app --reload
```

Run frontend:

```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\frontend"
npm run dev
```
