# V17 - ID photo alignment

- Added moveable ID photo crop/positioning in Add/Edit Staff form.
- Drag/drop photo into the ID placeholder and drag the image inside the placeholder to align the face.
- The aligned crop is saved as the uploaded ID photo, so ID cards and PDF exports use the corrected face position.
- View Staff and Edit Staff now show the existing saved photo in the ID photo placeholder.
- Backend staff list/detail responses now include `photo_url` and hide raw image bytes from JSON responses.

No new database changes are required beyond the existing profile photo columns.
