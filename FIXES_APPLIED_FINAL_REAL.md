# Final real patch

- Restored enterprise overview full-width lower blocks and full-width suggestions/notifications.
- Reworked digital ID CSS to stay white with no purple bars and improved long-name wrapping.
- Added staff-specific ID card PDF download: row button downloads only selected manager/employee.
- Kept optional all-staff export as a separate button.
- Fixed manager creation SQL value mismatch that could cause staff fetch/save failures.
- Added franchise registration website field support plus SuperUser edit form.
- Added backend PUT endpoint to edit franchise registration/profile details and keep approved franchise website in sync for QR links.
- QR target remains franchise website first, then office address fallback.
