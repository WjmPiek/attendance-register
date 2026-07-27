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


def test_office_code_expires_after_twenty_minutes():
    issued_at = datetime(2026, 7, 27, 12, 0)
    assert attendance._office_code_expiry(issued_at) == datetime(2026, 7, 27, 12, 20)


def test_successful_attendance_consumes_office_code():
    sign_in_source = inspect.getsource(attendance.sign_in)
    sign_out_source = inspect.getsource(attendance.sign_out)
    consume_source = inspect.getsource(attendance._consume_office_code)
    assert "_consume_office_code" in sign_in_source
    assert "_consume_office_code" in sign_out_source
    assert "qr_last_used_at" in consume_source
    assert "qr_expires_at > :now" in consume_source


def test_gps_distance_is_bound_to_entered_code_office():
    source = inspect.getsource(attendance._validate_gps)
    assert "office_area_id" in source
    assert "GPSAllocationPerUser.area_id == office_area_id" in source
    assert ".order_by(GPSAllocationPerUser.id.desc())" in source


def test_haversine_reports_real_world_kilometres():
    distance_m = attendance.haversine(-26.2041, 28.0473, -26.4290, 28.0473)
    assert 24_000 < distance_m < 26_000


class _MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class _NotificationDb:
    def execute(self, statement, params):
        return _MappingResult({
            "recipient_user_id": 22,
            "recipient_email": "manager@example.com",
        })


def test_outside_office_notifies_franchise_and_linked_manager(monkeypatch):
    created = []
    monkeypatch.setattr(attendance, "_attendance_franchise_recipient", lambda db, user_id: {
        "franchise_user_id": 4,
        "recipient_user_id": 11,
        "recipient_email": "franchise@example.com",
        "staff_name": "Remote Employee",
        "staff_type": "employee",
        "franchise_name": "Test Franchise",
    })
    monkeypatch.setattr(attendance, "create_notification", lambda db, **values: created.append(values))
    event = SimpleNamespace(
        id=91,
        user_id=7,
        action="sign_in",
        created_at=attendance.now_sa_naive(),
        attendance_status="outside_area",
        gps_status="outside_area",
        approval_status="pending",
        signature_status="captured",
        signature_image=b"signature",
        photo_status="captured",
        attendance_photo=b"photo",
        work_location_type="outside_area",
        latitude="-26.106851",
        longitude="27.811233",
        distance_from_site_m=25000,
    )

    attendance._notify_franchise_attendance_event(_NotificationDb(), event, "sign in")

    assert [item["recipient_user_id"] for item in created] == [11, 22]
    assert all(item["notification_type"] == "attendance_outside_area" for item in created)
    assert all(item["severity"] == "danger" for item in created)
    assert created[0]["target_tab"] == "approvals"
    assert created[1]["target_tab"] == "staff"
    assert "GPS coordinates: -26.106851, 27.811233" in created[0]["message"]


def test_attendance_events_persist_gps_coordinates():
    sign_in_source = inspect.getsource(attendance.sign_in)
    sign_out_source = inspect.getsource(attendance.sign_out)
    for source in (sign_in_source, sign_out_source):
        assert "latitude=str(payload.latitude)" in source
        assert "longitude=str(payload.longitude)" in source
        assert "accuracy_meters=str(accuracy)" in source
