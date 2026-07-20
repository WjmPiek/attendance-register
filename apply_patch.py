from pathlib import Path
import re
root=Path('/mnt/data/patchwork')

# schema auth
p=root/'backend/app/schemas/auth.py'
s=p.read_text()
s=s.replace('class LoginRequest(BaseModel):\n    email: EmailStr\n    password: str', 'class LoginRequest(BaseModel):\n    # Accept either an email address or a username in the same login field.\n    email: str\n    password: str')
s=s.replace('    email: EmailStr\n    roles:', '    email: Optional[str] = None\n    username: Optional[str] = None\n    roles:')
p.write_text(s)

# model User add username optional
p=root/'backend/app/models/core.py'
s=p.read_text()
s=s.replace('    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)\n    password_hash', '    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)\n    username: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)\n    password_hash')
p.write_text(s)

# schema migrations add username, website, irp5 manager column
p=root/'backend/app/services/schema_migrations.py'
s=p.read_text()
s=s.replace("        # Franchise/HR ownership and profile fields used by the staff API.\n", "        # Login compatibility: staff can sign in with either email or username.\n        _add_column(db, 'users', 'username', 'VARCHAR(100) UNIQUE')\n\n        # Franchise/HR ownership and profile fields used by the staff API.\n")
s=s.replace("        _add_column(db, 'franchise_users', 'office_address', 'TEXT')\n", "        _add_column(db, 'franchise_users', 'office_address', 'TEXT')\n        _add_column(db, 'franchise_users', 'website', 'VARCHAR(500)')\n")
s=s.replace("        _add_column(db, 'franchise_registrations', 'manager_note', 'TEXT')\n", "        _add_column(db, 'franchise_registrations', 'manager_note', 'TEXT')\n\n        # IRP5 manager ownership link.\n        _add_column(db, 'irp5_documents', 'manager_user_id', 'INTEGER')\n")
p.write_text(s)

# auth login dual
p=root/'backend/app/api/auth.py'
s=p.read_text()
s=s.replace('from sqlalchemy import text', 'from sqlalchemy import or_, text')
s=s.replace('    user = db.query(User).filter(User.email == payload.email).first()\n', '    login_value = (payload.email or "").strip()\n    user = db.query(User).filter(or_(User.email == login_value, User.username == login_value)).first()\n')
s=s.replace('        email=current_user.email,\n        roles=roles,', '        email=current_user.email,\n        username=getattr(current_user, "username", None),\n        roles=roles,')
p.write_text(s)

# frontend login wording and payload
p=root/'frontend/src/api/client.js'
s=p.read_text().replace("export async function login(email, password) {\n  return apiRequest('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })\n}", "export async function login(loginName, password) {\n  return apiRequest('/auth/login', { method: 'POST', body: JSON.stringify({ email: loginName, password }) })\n}")
p.write_text(s)
p=root/'frontend/src/App.jsx'
s=p.read_text().replace('const handleLogin = async (email, password) => {', 'const handleLogin = async (loginName, password) => {').replace('const data = await login(email, password)', 'const data = await login(loginName, password)')
p.write_text(s)
p=root/'frontend/src/pages/LoginPage.jsx'
s=p.read_text()
s=s.replace("const [email, setEmail] = useState('admin@example.com')", "const [email, setEmail] = useState('admin@example.com')")
s=s.replace('              <label>Email\n                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" required />\n              </label>', '              <label>Email or username\n                <input value={email} onChange={(event) => setEmail(event.target.value)} type="text" autoComplete="username" required />\n              </label>')
s=s.replace("Enter your email address first, then click Forgot password.", "Enter your email address first, then click Forgot password.")
p.write_text(s)

# franchise_staff robust patch
p=root/'backend/app/api/franchise_staff.py'
s=p.read_text()
# add import quote
s=s.replace('import zipfile\nfrom pathlib import Path', 'import zipfile\nfrom pathlib import Path\nfrom urllib.parse import quote_plus')
# add helpers after _safe_email
marker='def _ensure_profile_photo_columns(db: Session):'
helpers=r'''
def _safe_username(prefix: str, name: str, surname: str) -> str:
    clean_name = "".join(ch.lower() for ch in (name or "staff") if ch.isalnum()) or "staff"
    clean_surname = "".join(ch.lower() for ch in (surname or "user") if ch.isalnum()) or "user"
    return f"{prefix}_{clean_name}_{clean_surname}"


def _unique_username(db: Session, base: str) -> str:
    base = (base or "staff_user").strip("_")[:70] or "staff_user"
    candidate = base
    counter = 1
    while db.execute(text("SELECT 1 FROM users WHERE username = :username"), {"username": candidate}).first():
        counter += 1
        candidate = f"{base}_{counter}"
    return candidate


def _ensure_user_login_columns(db: Session):
    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100) UNIQUE"))
    db.execute(text("ALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL"))


def _staff_qr_target(db: Session, franchise_user_id: int | None, office_address: str | None = None) -> str:
    """QR target: franchise website first, otherwise office address in Google Maps."""
    website = None
    franchise_office = None
    if franchise_user_id:
        row = db.execute(text("""
            SELECT website, office_address
            FROM franchise_users
            WHERE id = :fid
            LIMIT 1
        """), {"fid": franchise_user_id}).mappings().first()
        if row:
            website = (row.get("website") or "").strip()
            franchise_office = (row.get("office_address") or "").strip()
    if website:
        if not website.lower().startswith(("http://", "https://")):
            website = "https://" + website
        return website
    address = (office_address or franchise_office or "").strip()
    if address:
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(address)
    return "https://martinsdirect.com"


def _qr_png_data_url(payload: str, pixels: int = 240) -> str | None:
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((pixels, pixels))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return None


'''
s=s.replace(marker, helpers+marker)
# ensure qrcode requirement later
# _ensure_profile_photo_columns add user/franchise columns
s=s.replace('    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL"))', '    _ensure_user_login_columns(db)\n    db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA NULL"))')
# replace _create_user function
s=re.sub(r'def _create_user\(db: Session, full_name: str, email: str, password: str, role_name: str\) -> int:[\s\S]*?\n\s*return user_id', r'''def _create_user(db: Session, full_name: str, email: str, password: str, role_name: str, username: str | None = None) -> int:
    _ensure_user_login_columns(db)
    existing = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).mappings().first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    username = _unique_username(db, username or email.split("@")[0])
    user_id = db.execute(text("""
        INSERT INTO users (full_name, email, username, password_hash, is_active, created_at, updated_at)
        VALUES (:full_name, :email, :username, :password_hash, TRUE, :now, :now)
        RETURNING id
    """), {
        "full_name": full_name,
        "email": email,
        "username": username,
        "password_hash": _hash_password(password),
        "now": datetime.utcnow(),
    }).scalar_one()

    db.execute(text("""
        INSERT INTO user_roles (user_id, role_id)
        VALUES (:user_id, :role_id)
        ON CONFLICT DO NOTHING
    """), {
        "user_id": user_id,
        "role_id": _role_id(db, role_name),
    })
    return user_id''', s, count=1)
# create manager/employee username and returns
s=s.replace('    login_email = str(payload.email) if payload.email else _safe_email("manager", payload.name, payload.surname)\n    user_id = _create_user(db, full_name, login_email, payload.password or "Temp123!", "ManagerUser")', '    login_email = str(payload.email) if payload.email else _safe_email("manager", payload.name, payload.surname)\n    login_username = _unique_username(db, _safe_username("manager", payload.name, payload.surname))\n    user_id = _create_user(db, full_name, login_email, payload.password or "Temp123!", "ManagerUser", login_username)')
s=s.replace('    return {"message": "Manager created", "manager_id": manager_id, "user_id": user_id}', '    return {"message": "Manager created", "manager_id": manager_id, "user_id": user_id, "username": login_username, "login_name": login_username if not payload.email else login_email}')
s=s.replace('    login_email = str(payload.email) if payload.email else _safe_email("employee", payload.name, payload.surname)\n    user_id = _create_user(db, full_name, login_email, payload.password or "Temp123!", "EmployeeUser")', '    login_email = str(payload.email) if payload.email else _safe_email("employee", payload.name, payload.surname)\n    login_username = _unique_username(db, _safe_username("employee", payload.name, payload.surname))\n    user_id = _create_user(db, full_name, login_email, payload.password or "Temp123!", "EmployeeUser", login_username)')
s=s.replace('    return {"message": "Employee created", "employee_id": employee_id, "user_id": user_id}', '    return {"message": "Employee created", "employee_id": employee_id, "user_id": user_id, "username": login_username, "login_name": login_username if not payload.email else login_email}')
# include website in card rows select and qr target in pdf
s=s.replace('fu.franchise_name, fu.business_name', 'fu.franchise_name, fu.business_name, fu.website, fu.office_address')
s=s.replace('fu.franchise_name, fu.business_name, fu.website, fu.office_address, fu.website, fu.office_address', 'fu.franchise_name, fu.business_name, fu.website, fu.office_address')
# pdf logo/qr dimensions
s=s.replace('logo = _logo_flowable(17, 10) or Paragraph(\'<b>LOGO</b>\', styles[\'CardSmall\'])\n        qr_payload = f"ARP-STAFF:{row.get(\'user_id\')}:{row.get(\'franchise_user_id\')}"\n        qr_drawing = _id_qr_drawing(qr_payload, 17)', 'logo = _logo_flowable(22, 22) or Paragraph(\'<b>LOGO</b>\', styles[\'CardSmall\'])\n        qr_payload = _staff_qr_target(db=None, franchise_user_id=None) if False else _staff_qr_target_for_pdf(row)\n        qr_drawing = _id_qr_drawing(qr_payload, 22)')
# Need define _staff_qr_target_for_pdf in build function? Better add nested before card
s=s.replace('    card_h = 53 * mm\n\n    def card(row):', '    card_h = 53 * mm\n\n    def _staff_qr_target_for_pdf(row):\n        website = (row.get("website") or "").strip()\n        if website:\n            if not website.lower().startswith(("http://", "https://")):\n                website = "https://" + website\n            return website\n        address = (row.get("office_address_assigned") or row.get("office_address") or "").strip()\n        if address:\n            return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(address)\n        return "https://martinsdirect.com"\n\n    def card(row):')
s=s.replace("top = Table([[qr_drawing, '', logo]], colWidths=[18*mm, 47*mm, 18*mm], rowHeights=[12*mm])", "top = Table([[qr_drawing, '', logo]], colWidths=[24*mm, 35*mm, 24*mm], rowHeights=[23*mm])")
s=s.replace("inner = Table([[top], [body], [bottom]], colWidths=[83*mm], rowHeights=[13*mm, 32*mm, 6*mm])", "inner = Table([[top], [body], [bottom]], colWidths=[83*mm], rowHeights=[24*mm, 21*mm, 6*mm])")
s=s.replace("body = Table([[photo, details]], colWidths=[25*mm, 58*mm], rowHeights=[31*mm])", "body = Table([[photo, details]], colWidths=[25*mm, 58*mm], rowHeights=[21*mm])")
# digital selects include website/office address if not already
s=s.replace('fu.franchise_name, fu.business_name\n        FROM employee_users', 'fu.franchise_name, fu.business_name, fu.website, fu.office_address\n        FROM employee_users')
s=s.replace('fu.franchise_name, fu.business_name\n            FROM manager_users', 'fu.franchise_name, fu.business_name, fu.website, fu.office_address\n            FROM manager_users')
# digital qr payload
s=s.replace('    qr_payload = f"ARP-STAFF:{data.get(\'user_id\')}:{data.get(\'franchise_user_id\') or \'\'}"', '    qr_payload = _staff_qr_target(db, data.get(\'franchise_user_id\'), data.get(\'office_address_assigned\') or data.get(\'office_address\'))\n    qr_image_url = _qr_png_data_url(qr_payload)')
s=s.replace("        'qr_payload': qr_payload,\n        'status': 'Active',", "        'qr_payload': qr_payload,\n        'qr_image_url': qr_image_url,\n        'status': 'Active',")
p.write_text(s)

# add qrcode to requirements
p=root/'backend/requirements.txt'
s=p.read_text()
if 'qrcode' not in s.lower():
    s += '\nqrcode[pil]>=7.4.2,<8.0\n'
p.write_text(s)

# IRP5 manager link
p=root/'backend/app/api/irp5.py'
s=p.read_text()
s=s.replace('            franchise_user_id INTEGER NULL,\n            original_filename', '            franchise_user_id INTEGER NULL,\n            manager_user_id INTEGER NULL,\n            original_filename')
s=s.replace('    db.commit()\n\n\ndef _employee_row', "    db.execute(text(\"ALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS manager_user_id INTEGER NULL\"))\n    db.commit()\n\n\ndef _employee_row")
s=s.replace('eu.name, eu.surname, eu.employee_role, u.full_name, u.email', 'eu.name, eu.surname, eu.employee_role, eu.manager_user_id, u.full_name, u.email')
s=s.replace('        INSERT INTO irp5_documents (employee_user_id, target_user_id, uploaded_by_user_id, franchise_user_id,\n            original_filename', '        INSERT INTO irp5_documents (employee_user_id, target_user_id, uploaded_by_user_id, franchise_user_id, manager_user_id,\n            original_filename')
s=s.replace('        VALUES (:employee_user_id, :target_user_id, :uploaded_by_user_id, :franchise_user_id,\n            :original_filename', '        VALUES (:employee_user_id, :target_user_id, :uploaded_by_user_id, :franchise_user_id, :manager_user_id,\n            :original_filename')
s=s.replace("'uploaded_by_user_id': current_user.id, 'franchise_user_id': employee['franchise_user_id'],", "'uploaded_by_user_id': current_user.id, 'franchise_user_id': employee['franchise_user_id'], 'manager_user_id': employee.get('manager_user_id'),")
p.write_text(s)

# frontend digital card show QR image
p=root/'frontend/src/components/DigitalIdCard.jsx'
s=p.read_text()
s=s.replace('            <div className="digital-id-qr-mini">\n              <span>STAFF</span>\n              <small>{card.user_id}</small>\n            </div>\n            <img className="digital-id-logo" src="/logo.png" alt="Martins logo" />', '            <div className="digital-id-qr-mini readable-qr">\n              {card.qr_image_url ? <img src={card.qr_image_url} alt="Staff QR code" /> : <><span>STAFF</span><small>{card.user_id}</small></>}\n            </div>\n            <img className="digital-id-logo" src="/logo.png" alt="Martins logo" />')
s=s.replace('<code>{card.qr_payload}</code>', '<a href={card.qr_payload} target="_blank" rel="noreferrer">Open linked site</a>')
p.write_text(s)

# CSS make same height
p=root/'frontend/src/styles.css'
s=p.read_text()
append='''\n\n/* Full patch: readable digital ID QR, bigger logo, same height */\n.digital-id-topline { align-items: center; gap: 14px; }\n.digital-id-qr-mini.readable-qr, .digital-id-logo { width: 96px !important; height: 96px !important; }\n.digital-id-qr-mini.readable-qr { display: flex; align-items: center; justify-content: center; background: #fff; border-radius: 14px; padding: 6px; }\n.digital-id-qr-mini.readable-qr img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; }\n.digital-id-logo { object-fit: contain; }\n'''
if 'Full patch: readable digital ID QR' not in s:
    s += append
p.write_text(s)

# SQL update file
p=root/'DATABASE_UPDATE_FULL_PATCH_IRP5_USERNAME_QR.sql'
p.write_text('''-- Full patch: IRP5 manager link, username login, and franchise QR website fallback\nALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100) UNIQUE;\nALTER TABLE franchise_users ADD COLUMN IF NOT EXISTS website VARCHAR(500);\nALTER TABLE irp5_documents ADD COLUMN IF NOT EXISTS manager_user_id INTEGER NULL;\n\n-- Backfill usernames for existing users that do not have one.\nUPDATE users\nSET username = LOWER(REGEXP_REPLACE(COALESCE(NULLIF(split_part(email, '@', 1), ''), 'user_' || id::text), '[^a-zA-Z0-9_]+', '_', 'g')) || '_' || id::text\nWHERE username IS NULL;\n''')
print('patched')
