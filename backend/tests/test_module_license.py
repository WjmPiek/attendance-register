import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer
from app.core import module_license as gate


def test_central_license_cache_expires_at_trial_boundary(monkeypatch):
    gate._cache.clear()
    monkeypatch.setattr(gate.settings,'ATTENDANCE_LAUNCH_SECRET','shared-test')
    clock=[1000]
    monkeypatch.setattr(gate.time,'time',lambda:clock[0])
    calls=[]
    class Reply:
        def raise_for_status(self): pass
        def json(self): return {'active':clock[0]<1005,'expires_at':1005}
    def post(url,**kwargs):
        assert url=='https://martinssystem.co.za/api/module-access'
        assert kwargs['timeout']==(2,3)
        signed=URLSafeTimedSerializer('shared-test',salt='martins-module-access-v1').loads(kwargs['json']['token'])
        assert signed=={'email':'holder@example.com','module':'attendance:view'}
        calls.append(1)
        return Reply()
    monkeypatch.setattr(gate.requests,'post',post)
    gate.require_email_license('holder@example.com')
    clock[0]=1004
    gate.require_email_license('holder@example.com')
    assert len(calls)==1
    clock[0]=1005
    with pytest.raises(HTTPException) as error:
        gate.require_email_license('holder@example.com')
    assert error.value.status_code==403 and len(calls)==2


def test_network_failure_denies_access_without_using_expired_cache(monkeypatch):
    gate._cache.clear()
    monkeypatch.setattr(gate.settings,'ATTENDANCE_LAUNCH_SECRET','shared-test')
    def fail(*args,**kwargs): raise gate.requests.Timeout()
    monkeypatch.setattr(gate.requests,'post',fail)
    with pytest.raises(HTTPException) as error:
        gate.require_email_license('holder@example.com')
    assert error.value.status_code==503


def test_staff_uses_owner_license_and_superuser_does_not_need_a_license(monkeypatch):
    from types import SimpleNamespace
    from app.models.core import User,FranchiseUser,UserRole,ManagerUser
    role_names=['Manager']
    class Query:
        def __init__(self,model):self.model=model
        def filter(self,*args):return self
        def all(self):return [SimpleNamespace(role=SimpleNamespace(name=n)) for n in role_names]
        def first(self):
            return SimpleNamespace(franchise_user_id=8) if self.model is ManagerUser else None
    class DB:
        def query(self,model):return Query(model)
        def get(self,model,id):
            return SimpleNamespace(user_id=9) if model is FranchiseUser else SimpleNamespace(email='owner@example.com')
    checked=[]
    monkeypatch.setattr(gate,'require_email_license',lambda email:checked.append(email))
    gate.require_user_license(DB(),SimpleNamespace(id=3,email='staff@example.com'))
    assert checked==['owner@example.com']
    role_names[:]=['SuperUser']
    gate.require_user_license(DB(),SimpleNamespace(id=3,email='admin@example.com'))
    assert checked==['owner@example.com']
