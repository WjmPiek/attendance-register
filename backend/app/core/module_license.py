"""Enforce central Martins module licences for native and SSO sessions."""
import time
from threading import Lock
import requests
from fastapi import HTTPException
from itsdangerous import URLSafeTimedSerializer
from app.core.config import settings

_cache={}
_lock=Lock()


def require_email_license(email):
    email=(email or '').strip().lower()
    current=time.time()
    with _lock:
        cached=_cache.get(email)
    if cached and cached[0]>current:
        active=cached[1]
    else:
        secret=settings.ATTENDANCE_LAUNCH_SECRET.strip()
        if not secret:
            raise HTTPException(status_code=503,detail='Module licensing is not configured. Contact Head Office.')
        signed=URLSafeTimedSerializer(secret,salt='martins-module-access-v1').dumps({'email':email,'module':'attendance:view'})
        try:
            response=requests.post('https://martinssystem.co.za/api/module-access',
                                  json={'module':'attendance:view','token':signed},timeout=(2,3))
            response.raise_for_status()
            data=response.json()
            if not isinstance(data,dict) or 'active' not in data:
                raise ValueError('Invalid licensing response')
        except (requests.RequestException,ValueError):
            raise HTTPException(status_code=503,detail='Cannot verify module access. Please try again shortly.')
        active=bool(data['active'])
        until=current+15
        if active and data.get('expires_at'):
            until=min(until,float(data['expires_at']))
        with _lock:
            if len(_cache)>2000:
                _cache.clear()
            _cache[email]=(until,active)
    if not active:
        raise HTTPException(status_code=403,detail='Attendance is inactive. Open My Modules in the Martins system and enter an activation code, or contact Head Office.')


def require_user_license(db,user):
    from app.models.core import User,UserRole,FranchiseUser,ManagerUser,EmployeeUser
    roles={ur.role.name for ur in db.query(UserRole).filter(UserRole.user_id==user.id).all()}
    if 'SuperUser' in roles:
        return
    owner=user
    profile=db.query(FranchiseUser).filter(FranchiseUser.user_id==user.id).first()
    if not profile:
        staff=db.query(ManagerUser).filter(ManagerUser.user_id==user.id).first()
        if not staff:
            staff=db.query(EmployeeUser).filter(EmployeeUser.user_id==user.id).first()
        if staff:
            profile=db.get(FranchiseUser,staff.franchise_user_id)
            owner=db.get(User,profile.user_id) if profile else None
    require_email_license(owner.email if owner else '')
