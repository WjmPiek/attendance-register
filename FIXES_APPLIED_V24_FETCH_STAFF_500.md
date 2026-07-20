# V24 Staff fetch 500 fix

Fixed `/api/franchise-staff/employees` and manager staff endpoints failing with 500 after the ID-card/photo patches.

Changes:
- Runtime migration now creates missing `profile_photo`, `profile_photo_mime`, and `profile_photo_filename` columns on `users`, `employee_users`, and `manager_users`.
- Fixed duplicated `franchise_user_id` column in manager creation SQL.
- The browser CORS message was caused by the backend 500. After this patch, restart the backend and hard refresh the frontend.
