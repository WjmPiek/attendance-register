from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

SA_TZ = ZoneInfo("Africa/Johannesburg")


def now_sa() -> datetime:
    return datetime.now(SA_TZ)


def now_sa_naive() -> datetime:
    return now_sa().replace(tzinfo=None)


def to_sa(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value
        return value.astimezone(SA_TZ).replace(tzinfo=None)
    return None


def format_sa_datetime(value, fallback: str = "n/a") -> str:
    dt = to_sa(value)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else fallback


def format_sa_date(value, fallback: str = "n/a") -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    dt = to_sa(value)
    return dt.strftime("%d/%m/%Y") if dt else fallback
