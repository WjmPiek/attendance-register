# Fixes Applied V8

- Added the Leave Return Planner visual block directly to the Leave tab.
- Employee users can now see approved leave periods and return dates under Leave Management.
- Reused the red/green timeline UI: red = on leave, green = back at work.
- Planner is aligned with the existing Leave page card layout and uses May 2026 by default.

Run as usual:

```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\backend"
uvicorn app.main:app --reload
```

```powershell
cd "D:\ATTENDANCE REGISTAR\attendance_register\frontend"
npm run dev
```
