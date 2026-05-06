# V22 Leave Return Planner Fix

- Leave return planner no longer shows only a hard-coded May 2026 view.
- It now includes every approved leave record in the current franchise/manager scope.
- It shows each user, leave dates, and the back-at-work date.
- Timeline sections are generated for each month that has approved leave.
- `/api/leave/applications` now returns `return_date` and orders leave by date.
