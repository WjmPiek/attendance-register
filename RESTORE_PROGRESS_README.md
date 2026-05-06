# Restore Progress + Franchise Edit Fix

This package restores the latest UI work and keeps the backend franchise edit routes.

Included:
- Enterprise overview/dashboard UI restored.
- Staff/digital ID card design restored.
- Franchise edit endpoints restored.
- Franchise website field retained for QR code linking.
- Safe SQL included.

Important: apply this package as the current project version. Do not apply older patch zips after this one, because older patches can overwrite the UI files.

After copying files:
1. Run DATABASE_FIX_SAFE_FRANCHISE_WEBSITE_STAFF.sql in DBeaver if not already run.
2. Restart backend:
   uvicorn app.main:app --reload
3. Restart frontend:
   npm run dev
4. Hard refresh browser with Ctrl+F5.
