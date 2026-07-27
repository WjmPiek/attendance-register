import base64
import inspect
from datetime import datetime
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


def test_outside_radius_is_recorded_for_office_attendance():
    source = inspect.getsource(attendance._validate_gps)
    assert "gps_status = 'outside_area'" in source
    assert "outside the allowed range of your assigned office" not in source
    assert "Range and accuracy exceptions are evidence" in source
    assert "outside the office GPS range and is pending review" in attendance._attendance_action_message("sign_in", "outside_area")


def test_outside_radius_remains_visible_on_session_report(monkeypatch):
    monkeypatch.setattr(attendance, "_is_missing_sign_out", lambda db, event, now=None: False)
    monkeypatch.setattr(attendance, "_user_display_context", lambda db, user_id: {"user_full_name": "Remote Employee"})
    base = attendance.now_sa_naive()
    sign_in = SimpleNamespace(
        id=31, user_id=9, action="sign_in", created_at=base,
        gps_status="outside_area", approval_status="pending",
        work_location_type="outside_area", is_late=False, late_minutes=0,
        latitude="-26.10", longitude="27.81",
    )
    sign_out = SimpleNamespace(
        id=32, user_id=9, action="sign_out", created_at=base,
        gps_status="inside_area", approval_status="pending",
        work_location_type="office", left_early=False, early_leave_minutes=0,
        latitude="-26.18", longitude="28.32",
    )
    session = attendance._build_sessions(object(), [sign_in, sign_out])[0]
    assert session["status"] == "outside_area"
    assert session["approval_status"] == "pending"


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


def test_office_code_week_rotates_on_monday():
    sunday_key, sunday_expiry = attendance._office_code_week(datetime(2026, 7, 26, 12, 0))
    monday_key, monday_expiry = attendance._office_code_week(datetime(2026, 7, 27, 12, 0))
    assert sunday_key == "2026-W30"
    assert sunday_expiry == datetime(2026, 7, 27, 0, 0)
    assert monday_key == "2026-W31"
    assert monday_expiry == datetime(2026, 8, 3, 0, 0)


def test_gps_distance_is_bound_to_entered_code_office():
    source = inspect.getsource(attendance._validate_gps)
    assert "office_area_id" in source
    assert "GPSAllocationPerUser.area_id == office_area_id" in source
    assert ".order_by(GPSAllocationPerUser.id.desc())" in source


def test_haversine_reports_real_world_kilometres():
    distance_m = attendance.haversine(-26.2041, 28.0473, -26.4290, 28.0473)
    assert 24_000 < distance_m < 26_000
