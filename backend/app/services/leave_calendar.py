"""Expected return dates follow the employee's recorded working week."""
from datetime import date, timedelta
from app.services.staff_hours import work_window


def return_to_work(end_date, staff, approved_ranges=()):
    candidate=date.fromisoformat(str(end_date)[:10])
    try:
        approved_ranges=[(date.fromisoformat(str(start)[:10]),date.fromisoformat(str(end)[:10])) for start,end in approved_ranges]
        candidate += timedelta(days=1)
        for _ in range(370):
            covered=[end for start,end in approved_ranges if start<=candidate<=end]
            if covered:
                candidate=max(covered)+timedelta(days=1)
                continue
            if work_window(staff,candidate.weekday()) is not None:
                return candidate
            candidate+=timedelta(days=1)
    except (ValueError,TypeError,OverflowError):
        return None
    return None
