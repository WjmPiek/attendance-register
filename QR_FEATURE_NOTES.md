# QR Office Attendance Feature

This build adds office-linked QR attendance.

## What was added

- Printable QR codes for each office/area.
- Franchise/Manager/SuperUser users can download the office QR PDF from **HR Staff > Office QR Codes**.
- Employees scan or enter the office QR code on **Mobile Sign In** before signing in or signing out.
- The scanned QR is validated against the employee's assigned GPS office/area.
- Attendance records store QR audit fields:
  - `qr_area_id`
  - `qr_office_name`
  - `qr_token_hash`
- Existing GPS and signature checks remain active.
- On-road attendance does not require QR, but still requires an employee note and approval.

## Database columns added lazily when QR endpoints/sign-in are used

```sql
ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_token VARCHAR(120);
ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE areas ADD COLUMN IF NOT EXISTS qr_updated_at TIMESTAMP NULL;
ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_area_id INTEGER NULL;
ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_office_name VARCHAR(255) NULL;
ALTER TABLE attendance_events ADD COLUMN IF NOT EXISTS qr_token_hash VARCHAR(128) NULL;
```

No startup migration was added, so backend startup remains stable.

## Use

Backend:

```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\backend"
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\frontend"
npm run dev
```
