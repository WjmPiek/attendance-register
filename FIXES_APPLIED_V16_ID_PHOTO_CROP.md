# Staff ID PDF photo crop fix

Fixed the Staff ID Cards PDF export so uploaded ID photos stay cropped inside the bordered photo block.

Changes made in `backend/app/api/franchise_staff.py`:

- Resized PDF ID photos to fit the actual photo cell.
- Cropped uploaded photos to the visible photo-box ratio before rendering.
- Added center alignment and tighter padding so images cannot overflow into card text, footer, or outside the card border.

This fixes the issue where uploaded images appeared outside the photo block on PDF ID cards.
