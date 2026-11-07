from datetime import date, datetime
from types import SimpleNamespace
import json

import pytest
from sqlalchemy import text

from app.api import leave
from app.services.leave_calendar import return_to_work
from tests.test_mortuary_book import database

WEEK=[{'start':'08:00','end':'17:00'}]*5+[None,None]


def test_return_date_uses_recorded_work_week_and_skips_adjacent_approved_leave():
    staff={'work_week':WEEK}
    assert return_to_work('2026-11-06',staff)==date(2026,11,9)
    assert return_to_work('2026-11-06',staff,[('2026-11-09','2026-11-11')])==date(2026,11,12)
    assert return_to_work('2026-12-31',staff)==date(2027,1,1)
    assert return_to_work('2026-11-06',{'work_week':[None]*7}) is None


@pytest.fixture
def leave_db(database,monkeypatch):
    db=database
    db.execute(text('''CREATE TABLE leave_applications(id INTEGER PRIMARY KEY,applicant_user_id INT,
        manager_user_id INT,franchise_user_id INT,leave_type TEXT,start_date DATE,end_date DATE,
        status TEXT,decision_note TEXT,created_at TEXT)'''))
    db.execute(text("INSERT INTO manager_users(id,user_id,franchise_user_id,name,surname,is_active,work_week) VALUES(7,12,2,'Example','Manager',TRUE,:week)"),{'week':json.dumps(WEEK)})
    db.execute(text('UPDATE employee_users SET manager_user_id=7,work_week=:week WHERE user_id=11'),{'week':json.dumps(WEEK)})
    for uid,mid,status,start,end in [(11,7,'approved','2026-11-02','2026-11-06'),(11,7,'declined','2025-01-01','2025-01-03'),(12,None,'approved','2026-12-01','2026-12-04'),(99,None,'approved','2026-11-02','2026-11-06')]:
        db.execute(text("INSERT INTO leave_applications(applicant_user_id,manager_user_id,franchise_user_id,leave_type,start_date,end_date,status,created_at) VALUES(:uid,:mid,:fid,'Annual Leave',:start,:end,:status,'2026-11-01')"),{'uid':uid,'mid':mid,'fid':99 if uid==99 else 2,'start':start,'end':end,'status':status})
    db.commit()
    monkeypatch.setattr(leave,'_ensure_tables',lambda db:None)
    monkeypatch.setattr(leave,'_roles',lambda db,user:{'ManagerUser' if user.id==12 else 'EmployeeUser'})
    monkeypatch.setattr(leave,'now_sa_naive',lambda:datetime(2026,11,7))
    return db


def test_staff_leave_history_contains_only_own_records_including_past_decisions(leave_db):
    rows=leave.list_leave_applications(current_user=SimpleNamespace(id=11),db=leave_db,own_only=True,include_past=True)
    assert len(rows)==2 and {r['applicant_user_id'] for r in rows}=={11}
    assert next(r for r in rows if r['status']=='approved')['return_date']==date(2026,11,9)
    assert not any(key.startswith('_work') for row in rows for key in row)


def test_manager_personal_page_does_not_mix_in_team_leave(leave_db):
    manager=SimpleNamespace(id=12)
    own=leave.list_leave_applications(current_user=manager,db=leave_db,own_only=True,include_past=True)
    assert {r['applicant_user_id'] for r in own}=={12}
    team=leave.list_leave_applications(current_user=manager,db=leave_db,include_past=True)
    assert {r['applicant_user_id'] for r in team}=={11,12}


def test_requesting_history_never_grants_access_to_another_staff_members_records(leave_db):
    own=leave.list_leave_applications(current_user=SimpleNamespace(id=11),db=leave_db,include_past=True)
    assert {r['applicant_user_id'] for r in own}=={11}
