# Global spacing / margins patch

- Added `frontend/src/styles_spacing_fix.css`.
- Imported it after `styles.css` in `frontend/src/main.jsx`.
- Adds consistent margins/padding around cards, forms, tables, dashboard blocks, notifications, suggestions, leave blocks, and staff blocks.
- Keeps text inset from block borders so values and labels do not sit flush against the block edge.
- Improves table cell padding and text wrapping for long names, long email addresses, website URLs, notes, and status text.
