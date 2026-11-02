"""The staff register owns weekly working hours used by attendance and commissions."""
from datetime import time
import json

from pydantic import BaseModel, Field, model_validator


class StaffWorkDay(BaseModel):
    start: str = Field(pattern=r'^\d{2}:\d{2}$')
    end: str = Field(pattern=r'^\d{2}:\d{2}$')

    @model_validator(mode='after')
    def valid_times(self):
        start, end = time.fromisoformat(self.start), time.fromisoformat(self.end)
        if start >= end:
            raise ValueError('End must be after start; untick the day when not working.')
        return self


def work_window(staff, weekday):
    week = staff.get('work_week')
    if isinstance(week, str):
        week = json.loads(week)
    if week is None:
        return {'start': staff.get('work_start_time') or '08:00', 'end': staff.get('work_end_time') or '17:00'}
    if not isinstance(week, list) or len(week) != 7:
        raise ValueError('Working week must list Monday through Sunday.')
    day = week[weekday]
    return StaffWorkDay(**day).model_dump() if day is not None else None
