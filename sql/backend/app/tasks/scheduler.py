from sqlalchemy import text
from apscheduler.schedulers.background import BackgroundScheduler

from app.db.session import SessionLocal
from app.api.alerts import send_daily_summary_email_for_franchise


scheduler = BackgroundScheduler(timezone="Africa/Johannesburg")


def franchise_has_alerts(db, franchise_id: int) -> bool:
    row = db.execute(text("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE franchise_user_id = :fid
          AND DATE(created_at) = CURRENT_DATE
    """), {"fid": franchise_id}).mappings().first()

    return bool(row and row["count"] > 0)


def run_franchise_daily_summary(franchise_id: int):
    db = SessionLocal()

    try:
        if not franchise_has_alerts(db, franchise_id):
            print(f"No alerts for franchise {franchise_id}; skipping summary email.")
            return

        send_daily_summary_email_for_franchise(
            franchise_id=franchise_id,
            db=db
        )

    except Exception as e:
        print(f"Daily summary failed for franchise {franchise_id}:", e)

    finally:
        db.close()


def start_scheduler():
    db = SessionLocal()

    try:
        franchises = db.execute(text("""
            SELECT id, daily_summary_time
            FROM franchise_users
            WHERE COALESCE(is_active, TRUE) = TRUE
              AND COALESCE(daily_summary_enabled, TRUE) = TRUE
        """)).mappings().all()

        for franchise in franchises:
            send_time = franchise["daily_summary_time"]

            scheduler.add_job(
                run_franchise_daily_summary,
                trigger="cron",
                hour=send_time.hour,
                minute=send_time.minute,
                args=[franchise["id"]],
                id=f"daily_summary_franchise_{franchise['id']}",
                replace_existing=True,
            )

        scheduler.start()
        print("Daily summary scheduler started.")

    finally:
        db.close()