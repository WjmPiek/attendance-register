from pathlib import Path
import re

ROOT = Path.cwd()
franchise_py = ROOT / 'backend' / 'app' / 'api' / 'franchise.py'
client_js = ROOT / 'frontend' / 'src' / 'api' / 'client.js'

if not franchise_py.exists():
    raise SystemExit(f'Cannot find {franchise_py}. Run this script from the attendance_register project root.')

s = franchise_py.read_text(encoding='utf-8')

# Make registration edit sync the live franchise_users row even when status values differ/case differs.
s = s.replace(
    'if updated and str(updated.get("status") or "").lower() == "approved":',
    'if updated:'
)

# Allow common frontend aliases in FranchiseRegistrationUpdate.
if 'business_registration: str | None = None' not in s and 'business_registration_number: str | None = None' in s:
    s = s.replace(
        'business_registration_number: str | None = None',
        'business_registration_number: str | None = None\n    business_registration: str | None = None'
    )
if 'vat_nr: str | None = None' not in s and 'vat_number: str | None = None' in s:
    s = s.replace(
        'vat_number: str | None = None',
        'vat_number: str | None = None\n    vat_nr: str | None = None'
    )
if 'contact: str | None = None' not in s and 'contact_number: str | None = None' in s:
    s = s.replace(
        'contact_number: str | None = None',
        'contact_number: str | None = None\n    contact: str | None = None'
    )

# Normalise alias names before allowed-list SQL building.
needle = '    data = payload.model_dump(exclude_unset=True)\n    if "website" in data:'
if needle in s and 'business_registration" in data' not in s[s.find(needle):s.find(needle)+600]:
    s = s.replace(needle, '''    data = payload.model_dump(exclude_unset=True)\n    # Accept both backend column names and common frontend field names.\n    if "business_registration" in data and "business_registration_number" not in data:\n        data["business_registration_number"] = data.pop("business_registration")\n    else:\n        data.pop("business_registration", None)\n    if "vat_nr" in data and "vat_number" not in data:\n        data["vat_number"] = data.pop("vat_nr")\n    else:\n        data.pop("vat_nr", None)\n    if "contact" in data and "contact_number" not in data:\n        data["contact_number"] = data.pop("contact")\n    else:\n        data.pop("contact", None)\n    if "website" in data:''')

append_code = r'''

# -----------------------------------------------------------------------------
# Live franchise profile edit endpoints
# SuperUser may edit any franchise profile.
# FranchiseUser may edit only the franchise profile linked to their own user_id.
# These endpoints update franchise_users.website, which is the value used by Staff ID QR codes.
# -----------------------------------------------------------------------------
class FranchiseUserUpdate(BaseModel):
    business_name: str | None = None
    trading_as: str | None = None
    franchise_name: str | None = None
    business_registration_number: str | None = None
    business_registration: str | None = None
    vat_number: str | None = None
    vat_nr: str | None = None
    office_address: str | None = None
    website: str | None = None
    office_number: str | None = None
    twenty_four_hour_number: str | None = None
    contact_number: str | None = None
    contact: str | None = None


def _is_superuser(db: Session, user: User) -> bool:
    return "SuperUser" in _role_names(db, user.id)


def _is_franchise_user(db: Session, user: User) -> bool:
    return "FranchiseUser" in _role_names(db, user.id)


def _normalise_franchise_user_payload(payload: FranchiseUserUpdate) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if "business_registration" in data and "business_registration_number" not in data:
        data["business_registration_number"] = data.pop("business_registration")
    else:
        data.pop("business_registration", None)
    if "vat_nr" in data and "vat_number" not in data:
        data["vat_number"] = data.pop("vat_nr")
    else:
        data.pop("vat_nr", None)
    if "contact" in data and "contact_number" not in data:
        data["contact_number"] = data.pop("contact")
    else:
        data.pop("contact", None)
    if "website" in data:
        data["website"] = _normalise_website(data.get("website"))
    if "trading_as" in data and "franchise_name" not in data:
        data["franchise_name"] = data.get("trading_as")
    return data


def _franchise_user_select_sql(where_sql: str) -> str:
    return f"""
        SELECT
            fu.id,
            fu.user_id,
            fu.franchise_name,
            fu.business_name,
            fu.trading_as,
            fu.business_registration_number,
            fu.vat_number,
            fu.office_address,
            fu.website,
            fu.office_number,
            fu.twenty_four_hour_number,
            fu.contact_number,
            fu.is_active,
            u.email,
            u.full_name
        FROM franchise_users fu
        LEFT JOIN users u ON u.id = fu.user_id
        WHERE {where_sql}
    """


def _require_franchise_profile_access(db: Session, current_user: User, franchise_user_id: int | None = None):
    if _is_superuser(db, current_user):
        return
    if not _is_franchise_user(db, current_user):
        raise HTTPException(status_code=403, detail="Only SuperUser or FranchiseUser can edit franchise details")
    if franchise_user_id is None:
        return
    own = db.execute(text("SELECT id FROM franchise_users WHERE id = :fid AND user_id = :uid LIMIT 1"), {
        "fid": franchise_user_id,
        "uid": current_user.id,
    }).mappings().first()
    if not own:
        raise HTTPException(status_code=403, detail="You can only edit your own franchise details")


def _update_live_franchise_user(franchise_user_id: int, payload: FranchiseUserUpdate, current_user: User, db: Session):
    _ensure_franchise_website_schema(db)
    _require_franchise_profile_access(db, current_user, franchise_user_id)
    existing = db.execute(text(_franchise_user_select_sql("fu.id = :fid") + " LIMIT 1"), {"fid": franchise_user_id}).mappings().first()
    if not existing:
        raise HTTPException(status_code=404, detail="Franchise user not found")

    data = _normalise_franchise_user_payload(payload)
    allowed = [
        "franchise_name", "business_name", "trading_as", "business_registration_number", "vat_number",
        "office_address", "website", "office_number", "twenty_four_hour_number", "contact_number",
    ]
    data = {k: v for k, v in data.items() if k in allowed}
    if not data:
        return dict(existing)

    sets = [f"{k} = :{k}" for k in data.keys()]
    params = {**data, "fid": franchise_user_id, "updated_at": datetime.utcnow()}
    updated = db.execute(text(f"""
        UPDATE franchise_users
        SET {', '.join(sets)}, updated_at = :updated_at
        WHERE id = :fid
        RETURNING *
    """), params).mappings().first()

    # Keep matching approved registration in sync too, when the email links both records.
    if updated:
        user_email = db.execute(text("SELECT email FROM users WHERE id = :uid"), {"uid": updated.get("user_id")}).scalar()
        if user_email:
            reg_sets = []
            reg_params = {"email": user_email, "updated_at": datetime.utcnow()}
            for source in [
                "business_name", "trading_as", "business_registration_number", "vat_number",
                "office_address", "website", "office_number", "twenty_four_hour_number", "contact_number",
            ]:
                if source in data:
                    reg_sets.append(f"{source} = :{source}")
                    reg_params[source] = data[source]
            if reg_sets:
                db.execute(text(f"""
                    UPDATE franchise_registrations
                    SET {', '.join(reg_sets)}, updated_at = :updated_at
                    WHERE LOWER(email) = LOWER(:email)
                """), reg_params)

    db.commit()
    refreshed = db.execute(text(_franchise_user_select_sql("fu.id = :fid") + " LIMIT 1"), {"fid": franchise_user_id}).mappings().first()
    return dict(refreshed) if refreshed else dict(updated)


@router.get("/users")
def list_franchise_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    if _is_superuser(db, current_user):
        rows = db.execute(text(_franchise_user_select_sql("1=1") + " ORDER BY fu.id DESC")).mappings().all()
        return {"items": [dict(r) for r in rows]}
    if _is_franchise_user(db, current_user):
        rows = db.execute(text(_franchise_user_select_sql("fu.user_id = :uid") + " ORDER BY fu.id DESC"), {"uid": current_user.id}).mappings().all()
        return {"items": [dict(r) for r in rows]}
    raise HTTPException(status_code=403, detail="Not allowed")


@router.get("/me")
def get_my_franchise_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    _require_franchise_profile_access(db, current_user)
    row = db.execute(text(_franchise_user_select_sql("fu.user_id = :uid") + " LIMIT 1"), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    return dict(row)


@router.put("/users/{franchise_user_id}")
def update_franchise_user_put(franchise_user_id: int, payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_user(franchise_user_id, payload, current_user, db)


@router.patch("/users/{franchise_user_id}")
def update_franchise_user_patch(franchise_user_id: int, payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _update_live_franchise_user(franchise_user_id, payload, current_user, db)


@router.put("/me")
def update_my_franchise_profile_put(payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    row = db.execute(text("SELECT id FROM franchise_users WHERE user_id = :uid LIMIT 1"), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    return _update_live_franchise_user(row["id"], payload, current_user, db)


@router.patch("/me")
def update_my_franchise_profile_patch(payload: FranchiseUserUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_franchise_website_schema(db)
    row = db.execute(text("SELECT id FROM franchise_users WHERE user_id = :uid LIMIT 1"), {"uid": current_user.id}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Franchise profile not found")
    return _update_live_franchise_user(row["id"], payload, current_user, db)
'''

if 'Live franchise profile edit endpoints' not in s:
    s = s.rstrip() + append_code + '\n'

franchise_py.write_text(s, encoding='utf-8')
print('[OK] patched backend/app/api/franchise.py')

if client_js.exists():
    c = client_js.read_text(encoding='utf-8')
    additions = ''
    if 'updateFranchiseRegistration(' not in c:
        additions += '''\nexport async function updateFranchiseRegistration(registrationId, payload) {\n  return apiRequest(`/franchise/registrations/${registrationId}/edit`, { method: 'PATCH', body: JSON.stringify(payload) })\n}\n'''
    if 'updateFranchiseUser(' not in c:
        additions += '''\nexport async function updateFranchiseUser(franchiseUserId, payload) {\n  return apiRequest(`/franchise/users/${franchiseUserId}`, { method: 'PATCH', body: JSON.stringify(payload) })\n}\n'''
    if 'getFranchiseUsers(' not in c:
        additions += '''\nexport async function getFranchiseUsers() {\n  return apiRequest('/franchise/users')\n}\n\nexport async function getMyFranchiseProfile() {\n  return apiRequest('/franchise/me')\n}\n\nexport async function updateMyFranchiseProfile(payload) {\n  return apiRequest('/franchise/me', { method: 'PATCH', body: JSON.stringify(payload) })\n}\n'''
    if additions:
        c = c.rstrip() + '\n' + additions
        client_js.write_text(c, encoding='utf-8')
        print('[OK] patched frontend/src/api/client.js')
    else:
        print('[OK] frontend/src/api/client.js already has franchise edit helpers')
else:
    print('[WARN] frontend/src/api/client.js not found; backend patch still applied')

print('\nDone. Restart backend and frontend after running the SQL file.')
