from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
import os
import smtplib
import ssl
from typing import Any

from app.core.timezone import now_sa_naive


@dataclass
class EmailConfig:
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_from_name: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    smtp_timeout_seconds: int
    config_source: str

    @property
    def configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_username and self.smtp_password and (self.smtp_from_email or self.smtp_username))

    def safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["smtp_password"] = "set" if self.smtp_password else "missing"
        data["configured"] = self.configured
        return data


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _candidate_env_paths() -> list[Path]:
    here = Path(__file__).resolve()
    backend_dir = here.parents[2]
    return [Path.cwd() / ".env", backend_dir / ".env", backend_dir.parent / ".env"]


def _load_env_values() -> tuple[dict[str, str], str]:
    merged: dict[str, str] = {}
    used: list[str] = []
    for p in _candidate_env_paths():
        vals = _parse_env_file(p)
        if vals:
            merged.update(vals)
            used.append(str(p))
    for key, value in os.environ.items():
        if key.startswith("SMTP_"):
            merged[key] = value
            used.append("process-environment")
    return merged, ", ".join(dict.fromkeys(used)) or "none"


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_email_config() -> EmailConfig:
    values, source = _load_env_values()
    host = values.get("SMTP_HOST") or None
    username = values.get("SMTP_USERNAME") or None
    password = values.get("SMTP_PASSWORD") or None
    if password:
        password = "".join(str(password).split())
    from_email = values.get("SMTP_FROM_EMAIL") or username
    try:
        port = int(values.get("SMTP_PORT") or 587)
    except Exception:
        port = 587
    use_ssl = _bool(values.get("SMTP_USE_SSL"), default=(port == 465))
    use_tls = _bool(values.get("SMTP_USE_TLS"), default=(not use_ssl))
    try:
        timeout = int(values.get("SMTP_TIMEOUT_SECONDS") or 30)
    except Exception:
        timeout = 30
    return EmailConfig(
        smtp_host=host,
        smtp_port=port,
        smtp_username=username,
        smtp_password=password,
        smtp_from_email=from_email,
        smtp_from_name=values.get("SMTP_FROM_NAME") or "Attendance Register Platform",
        smtp_use_tls=use_tls,
        smtp_use_ssl=use_ssl,
        smtp_timeout_seconds=timeout,
        config_source=source,
    )


def _valid_email(address: str | None) -> bool:
    if not address:
        return False
    parsed = parseaddr(address)[1]
    return bool(parsed and "@" in parsed and "." in parsed.rsplit("@", 1)[-1])


def send_smtp_email(recipient_email: str | None, subject: str, message: str) -> tuple[str, datetime | None, str | None, dict[str, Any]]:
    cfg = get_email_config()
    diagnostics = cfg.safe_dict()
    diagnostics["recipient_email"] = recipient_email
    if not _valid_email(recipient_email):
        return "pending", None, "No valid recipient email set", diagnostics
    if not cfg.smtp_host:
        return "pending", None, "SMTP_HOST is not configured. Check backend/.env.", diagnostics
    if not cfg.smtp_username:
        return "pending", None, "SMTP_USERNAME is not configured. Check backend/.env.", diagnostics
    if not cfg.smtp_password:
        return "pending", None, "SMTP_PASSWORD is not configured. Use a Gmail App Password, not the normal Gmail password.", diagnostics
    if not _valid_email(cfg.smtp_from_email):
        return "pending", None, "SMTP_FROM_EMAIL is missing or invalid.", diagnostics

    try:
        email = EmailMessage()
        email["From"] = formataddr((cfg.smtp_from_name, cfg.smtp_from_email or cfg.smtp_username or ""))
        email["To"] = recipient_email or ""
        email["Subject"] = subject
        email.set_content(message)
        if cfg.smtp_use_ssl:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds, context=ssl.create_default_context()) as smtp:
                smtp.login(cfg.smtp_username, cfg.smtp_password)
                smtp.send_message(email)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.smtp_timeout_seconds) as smtp:
                smtp.ehlo()
                if cfg.smtp_use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                smtp.login(cfg.smtp_username, cfg.smtp_password)
                smtp.send_message(email)
        return "sent", now_sa_naive(), None, diagnostics
    except smtplib.SMTPAuthenticationError as exc:
        return "failed", None, "SMTP authentication failed. For Gmail, enable 2-Step Verification and generate a new App Password. " + str(exc), diagnostics
    except Exception as exc:
        return "failed", None, str(exc)[:1000], diagnostics
