# Martins Attendance - Enhanced Build

Included in this bundle:

- Final Overview leave visibility enhancements for Franchise/Manager scope
- Leave applications by approval status with All / Approved / Pending / Declined / Rejected filtering
- Leave calendar / staff-away block showing approved current/upcoming leave, return date and days
- Payroll Management module
  - Payroll tab for SuperUser, FranchiseUser and Finance employees
  - Employee/manager payroll setup
  - Basic salary, hourly rate, allowances, deductions, PAYE %, UIF %, pay frequency
  - Monthly payroll preview
  - Draft payroll run saving
  - Payroll summary totals: gross, deductions, net pay
  - Payroll calculations include attendance days, approved leave days, late count and missing sign-out count
- Mobile spacing and table overflow improvements

Backend route added:

- `/api/payroll/employees`
- `/api/payroll/settings`
- `/api/payroll/preview`
- `/api/payroll/runs`

Runtime database tables added automatically:

- `payroll_settings`
- `payroll_runs`

Note: This build source is packaged ready to install. The frontend build was not compiled in this environment because `vite` is not installed here. Run `npm install` then `npm run build` inside `/frontend` on your machine.
