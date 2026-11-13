"""Unit coverage for the private election scheduling utilities."""
from datetime import datetime
from fastapi import HTTPException
import pytest
from app.prwahl_schedule import local_to_utc, display_local, calendar_file

def test_berlin_local_time_to_utc():
    assert local_to_utc("2026-11-13T10:30") == datetime(2026, 11, 13, 9, 30)
    assert display_local(datetime(2026, 11, 13, 9, 30)) == "13.11.2026 10:30"

def test_nonexistent_dst_time_is_rejected():
    with pytest.raises(HTTPException):
        local_to_utc("2026-03-29T02:30")

def test_calendar_export_escapes_text_and_uses_utc():
    class Event:
        uid = "example@takt-prwahl"
        title = "Sitzung, Wahlvorstand; intern"
        location = "Raum 1"
        starts_at = datetime(2026, 11, 13, 9)
        ends_at = datetime(2026, 11, 13, 10)
        updated_at = datetime(2026, 11, 1, 9)
        created_at = updated_at
        sequence = 0
        status = "planned"
    result = calendar_file(Event())
    assert "DTSTART:20261113T090000Z" in result
    assert "Sitzung\\, Wahlvorstand\\; intern" in result
    assert result.endswith("\r\n")

def test_ambiguous_autumn_time_is_rejected():
    with pytest.raises(HTTPException):
        local_to_utc("2026-10-25T02:30")
