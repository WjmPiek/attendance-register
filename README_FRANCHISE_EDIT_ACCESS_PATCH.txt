Franchise edit access patch

What this fixes:
- SuperUser can edit any franchise profile data.
- FranchiseUser can edit only their own franchise profile.
- Website saves to franchise_users.website, which staff ID QR code should read.
- Franchise registration edits sync to live franchise profile.
- Accepts common frontend aliases: business_registration, vat_nr, contact.

How to apply:
1. Extract this zip into your project root: D:\ATTENDANCE REGISTAR\attendance_register
2. Run:
   python APPLY_FRANCHISE_EDIT_ACCESS_PATCH.py
3. Run DATABASE_FRANCHISE_EDIT_ACCESS_SAFE.sql in DBeaver.
4. Restart backend:
   cd "D:\ATTENDANCE REGISTAR\attendance_register\backend"
   uvicorn app.main:app --reload
5. Restart frontend:
   cd "D:\ATTENDANCE REGISTAR\attendance_register\frontend"
   npm run dev
