"""Booking staff notification preferences and pending-request escalation."""
import json
import secrets
from datetime import datetime, timedelta

from starlette.datastructures import FormData

from app import booking_integration, bookings
from app.db import Booking, BookingPage
from app.routes_bookings import _apply
from test_native_tasks import task_people


def _fixture_booking(db, owner, provider=None, *, settings=None, status="requested"):
    page = BookingPage(
        owner_id=owner.id,
        title="Test-Sprechstunde",
        public_token=secrets.token_hex(20),
        integration_json=json.dumps(settings or {}),
        notify_owner=True,
    )
    db.add(page)
    db.flush()
    now = datetime(2027, 1, 1, 12)
    appointment = Booking(
        page_id=page.id,
        provider_id=provider.id if provider else None,
        name="Geheim Mustermann", email="geheim@example.org",
        token=secrets.token_hex(20),
        starts_at=now + timedelta(days=4),
        ends_at=now + timedelta(days=4, minutes=30),
        created_at=now - timedelta(days=2),
        status=status,
    )
    db.add(appointment)
    db.flush()
    return page, appointment, now


def test_owner_can_filter_information_but_assigned_staff_still_notified(db, task_people, monkeypatch):
    owner, provider = task_people[:2]
    page, booking, _ = _fixture_booking(db, owner, provider, settings={
        "owner_mail_events": ["request"]
    })
    sent = []
    monkeypatch.setattr(bookings.notify, "enqueue",
                        lambda db, to_addr, subject, body, kind, cfg, **kwargs:
                        sent.append((to_addr, kind, body)) or True)
    try:
        bookings._notify_owner(db, booking, "Neue Buchung")
        assert [email for email, _, _ in sent] == [provider.email]
        sent.clear()
        bookings._notify_owner(db, booking, "Neue Anfrage – bitte bestätigen")
        assert {email for email, _, _ in sent} == {owner.email, provider.email}

        # A pending request with an inactive provider must still notify the
        # page owner, even when they disabled informational booking messages.
        sent.clear()
        page.notify_owner = False
        provider.active = False
        db.flush()
        bookings._notify_owner(db, booking, "Neue Anfrage – bitte bestätigen")
        assert [email for email, _, _ in sent] == [owner.email]
    finally:
        provider.active = True
        db.delete(booking)
        db.delete(page)
        db.commit()


def test_esc_due_only_once_and_contains_no_guest_data(db, task_people, monkeypatch):
    owner = task_people[0]
    page, booking, now = _fixture_booking(db, owner, settings={
        "request_escalation_hours": 24,
    })
    messages = []
    monkeypatch.setattr(bookings.notify, "enqueue",
                        lambda db, email, subject, body, kind, cfg, **kwargs:
                        messages.append((email, subject, body, kind)) or True)
    try:
        assert bookings.escalate_pending_requests(db, now=now) == 1
        assert booking.escalated_at == now
        assert bookings.escalate_pending_requests(db, now=now) == 0
        assert len(messages) == 1
        assert messages[0][0] == owner.email
        assert messages[0][3] == "booking_escalation"
        assert "Geheim Mustermann" not in messages[0][2]
        assert "geheim@example.org" not in messages[0][2]
        assert booking.token not in messages[0][2]
        assert f"/bookings/{page.id}" in messages[0][2]

        booking.escalated_at = None
        booking.status = "booked"
        db.flush()
        assert bookings.escalate_pending_requests(db, now=now) == 0
    finally:
        db.delete(booking)
        db.delete(page)
        db.commit()


def test_escalation_retry_when_queue_unavailable(db, task_people, monkeypatch):
    owner = task_people[0]
    page, booking, now = _fixture_booking(db, owner, settings={
        "request_escalation_hours": 4,
    })
    monkeypatch.setattr(bookings.notify, "enqueue", lambda *args, **kwargs: False)
    try:
        assert bookings.escalate_pending_requests(db, now=now) == 0
        assert booking.escalated_at is None
    finally:
        db.delete(booking)
        db.delete(page)
        db.commit()


def test_notification_settings_validate_and_keep_page_defaults(db, task_people):
    owner = task_people[0]
    page = BookingPage(owner_id=owner.id, title="Alt", public_token=secrets.token_hex(12),
                       notify_owner=True, integration_json='{"external_calendar":"busy"}')
    # Only use the existing entry point to save these settings; do not add
    # a second route that bypasses booking-page EDIT access checks.
    data = FormData([
        ("title", "Termine"),
        ("notify_owner", "1"),
        ("integration_form", "1"),
        ("owner_mail_events", "new"),
        ("owner_mail_events", "cancel"),
        ("request_escalation_hours", "24"),
    ])
    _apply(page, data)
    assert booking_integration.owner_mail_enabled(page, "Neue Buchung")
    assert booking_integration.owner_mail_enabled(page, "Absage")
    assert not booking_integration.owner_mail_enabled(page, "Termin verschoben")
    assert booking_integration.escalation_hours(page) == 24

    opts = booking_integration.options(page)
    assert opts["owner_mail_events"] == ["new", "cancel"]
    assert opts["request_escalation_hours"] == 24
    assert opts["external_calendar"] == "busy"
    assert booking_integration.escalation_hours(
        BookingPage(integration_json='{"request_escalation_hours":99999}')
    ) == 0
