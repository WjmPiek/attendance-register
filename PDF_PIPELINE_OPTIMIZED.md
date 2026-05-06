# PDF pipeline optimized

What changed:

- Single staff ID downloads now render one CR80 card on a small 94mm x 64mm PDF page instead of building the full all-staff grid.
- Staff photos are cropped and downscaled before PDF rendering, which reduces PDF size and generation time.
- The PDF export no longer runs schema ALTER checks on every download. Run the database update SQL once before using the feature.
- Batch export is still available, but individual staff buttons use `staff_type` + `staff_id` and should download only that one card.
- Response headers now include `Content-Length` and `Cache-Control: no-store` for cleaner downloads.

Safe SQL reminder:

Use `ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, and `CREATE INDEX IF NOT EXISTS`. Avoid repeated plain `INSERT` statements unless they include `ON CONFLICT` or `WHERE NOT EXISTS`.
