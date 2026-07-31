# Microsoft 365 SMTP on Render

Use these Render environment variables for the Attendance Register backend:

```env
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=attendance@martinssystem.co.za
SMTP_PASSWORD=<mailbox-password-or-app-password>
SMTP_FROM_EMAIL=attendance@martinssystem.co.za
SMTP_FROM_NAME=Martins Attendance Register
SMTP_USE_TLS=true
SMTP_USE_SSL=false
```

The mailbox must allow authenticated SMTP. In Microsoft 365/Exchange admin, enable SMTP AUTH for `attendance@martinssystem.co.za` if it is disabled.

After deploy, sign in as a SuperUser and use the authenticated app/API endpoints:

```http
GET /api/alerts/email-config
POST /api/alerts/email-test
POST /api/alerts/email-retry-pending
```

The system sends notification emails when `recipient_email` is set on notifications. Attendance outside-office events notify the owning franchise user and the assigned manager. Leave applications notify the franchise/manager reviewer.
