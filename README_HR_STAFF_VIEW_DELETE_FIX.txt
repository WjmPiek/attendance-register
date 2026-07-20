HR Staff View/Delete Fix

What this fixes:
- Manager delete button now uses a POST delete route and refreshes the list.
- Employee delete button now uses a POST delete route and refreshes the list.
- Deleted staff are hidden from My Managers/My Employees lists.
- Employee View scrolls the detail panel into view, so it is clear that the View button worked.
- Backend keeps records in the database by setting is_active=false; it does not hard-delete records.

How to apply:
1. Extract this zip into your project root:
   D:\ATTENDANCE REGISTAR\attendance_register
2. Run:
   python APPLY_HR_STAFF_VIEW_DELETE_FIX.py
3. Restart backend:
   cd backend
   uvicorn app.main:app --reload
4. Restart frontend:
   cd frontend
   npm run dev
5. Hard refresh browser: Ctrl + F5
