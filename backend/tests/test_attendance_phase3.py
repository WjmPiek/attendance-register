import base64
import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import attendance
from app.schemas.attendance import AttendanceActionRequest


class _EmptyQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class _RulesDb:
    def query(self, *args, **kwargs):
        return _EmptyQuery()


def _request(**changes):
    values = {
        "latitude": -26.2041,
        "longitude": 28.0473,
        "accuracy": 12,
        "signature_value": "data:image/png;base64,AA==",
        "photo_value": "data:image/jpeg;base64,AA==",
        "work_location_type": "office",
    }
    values.update(changes)
    return AttendanceActionRequest(**values)


def test_gps_is_required_even_without_a_gps_rule(monkeypatch):
    monkeypatch.setattr(attendance, "_require_employee_access", lambda db, user: None)
    with pytest.raises(HTTPException, match="GPS location is required"):
        attendance._validate_rules(
            _RulesDb(),
            SimpleNamespace(id=1),
            _request(latitude=None),
            True,
        )


def test_signature_and_automatic_photo_are_required(monkeypatch):
    monkeypatch.setattr(attendance, "_require_employee_access", lambda db, user: None)
    with pytest.raises(HTTPException, match="Signature is required"):
        attendance._validate_rules(
            _RulesDb(),
            SimpleNamespace(id=1),
            _request(signature_value=None),
            True,
        )
    with pytest.raises(HTTPException, match="Automatic attendance photo is required"):
        attendance._validate_rules(
            _RulesDb(),
            SimpleNamespace(id=1),
            _request(photo_value=None),
            True,
        )


def test_attendance_photo_decoder_accepts_captured_jpeg():
    value = "data:image/jpeg;base64," + base64.b64encode(b"jpeg-bytes").decode()
    image, mime, filename = attendance._photo_data_url_to_image(value, "sign_in", 7)
    assert image == b"jpeg-bytes"
    assert mime == "image/jpeg"
    assert filename.startswith("attendance_user_7_sign_in_")


def test_four_digit_office_code_is_required_in_sign_in_and_sign_out():
    sign_in_source = inspect.getsource(attendance.sign_in)
    sign_out_source = inspect.getsource(attendance.sign_out)
    assert "and payload.qr_value" not in sign_in_source
    assert "and payload.qr_value" not in sign_out_source
    assert "_validate_office_qr_for_user" in sign_in_source
    assert "_validate_office_qr_for_user" in sign_out_source


def test_outside_radius_is_rejected_for_office_attendance():
    source = inspect.getsource(attendance._validate_gps)
    assert "gps_status = 'outside_area'" in source
    assert "outside the allowed range of your assigned office" in source


def test_open_session_is_returned_before_sign_out(monkeypatch):
    monkeypatch.setattr(attendance, "_is_missing_sign_out", lambda db, event, now=None: False)
    monkeypatch.setattr(
        attendance,
        "_user_display_context",
        lambda db, user_id: {"user_full_name": "Open Employee"},
    )
    sign_in = SimpleNamespace(
        id=17,
        user_id=8,
        action="sign_in",
        created_at=attendance.now_sa_naive(),
        gps_status="inside_area",
        approval_status="pending",
        work_location_type="office",
        is_late=False,
        late_minutes=0,
        latitude="-26.1",
        longitude="28.1",
    )
    sessions = attendance._build_sessions(object(), [sign_in])
    assert len(sessions) == 1
    assert sessions[0]["status"] == "open"
    assert sessions[0]["sign_in_event_id"] == 17
    assert sessions[0]["sign_out_event_id"] is None
