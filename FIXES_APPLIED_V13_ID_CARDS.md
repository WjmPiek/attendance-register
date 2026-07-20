ID CARD GENERATOR V13

Added:
- HR Staff > ID Cards tab: batch PDF generator per franchise.
- HR Staff action button: Upload ID Photo for employees and managers.
- Backend endpoint: POST /api/franchise-staff/{employees|managers}/{id}/photo.
- Backend endpoint: GET /api/franchise-staff/id-cards/export.
- Attendance PDF exports now print the stored ID photo and QR scan status/office.
- DBeaver SQL included in DATABASE_UPDATE_ID_CARDS_AND_QR.sql.

Run SQL first, then restart backend using:
uvicorn app.main:app --reload
