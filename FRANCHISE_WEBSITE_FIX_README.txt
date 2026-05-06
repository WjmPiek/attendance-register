Fixes franchise website add/edit.

Apply steps:
1. Copy these files into your project, replacing existing files.
2. In DBeaver, run DATABASE_FIX_FRANCHISE_WEBSITE_FINAL.sql.
3. Restart backend with: uvicorn app.main:app --reload
4. Restart frontend with: npm run dev
5. Hard refresh browser with Ctrl+F5.

This patch adds/keeps website fields on franchise registration and approved franchise profiles, normalises URLs, and makes the frontend Save button fallback to the older /edit route if needed.
