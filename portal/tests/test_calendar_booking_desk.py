"""Calendar booking desk shows only assigned or genuinely shared appointment data."""
import json
import secrets
from datetime import datetime, timedelta

from app.db import Booking, BookingPage, get_settings, utcnow
from conftest import login, settings
from test_native_tasks import task_people


def test_booking_calendar_overview_redacts_and_scopes_private_guests(db, task_people):
    owner, assigned, outsider = task_people[:3]
    old = get_settings(db)
    settings(module_bookings="1", module_calendars="1")
    page = BookingPage(
        owner_id=owner.id, title="Beratungsstelle",
        public_token=secrets.token_hex(20),
        integration_json=json.dumps({"calendar_privacy": "assigned"}),
    )
    db.add(page)
    db.flush()
    starts = utcnow() + timedelta(days=6)
    booking = Booking(
        page_id=page.id, provider_id=assigned.id,
        starts_at=starts, ends_at=starts + timedelta(minutes=45),
        status="requested", name="Erika Geheim", email="erika@example.org",
        token=secrets.token_hex(20),
    )
    db.add(booking)
    db.commit()
    try:
        own = login(assigned.email, "task-passwort-123")
        response = own.get("/kalender/buchungen")
        assert response.status_code == 200
        assert "Erika Geheim" in response.text
        assert f"/kalender/buchungen/{booking.id}/bestaetigen" in response.text
        assert "Bestätigung ausstehend" in response.text

        without_role = login(outsider.email, "task-passwort-123")
        invisible = without_role.get("/kalender/buchungen?scope=team")
        assert invisible.status_code == 200
        assert "Erika Geheim" not in invisible.text
        assert "Beratungsstelle" not in invisible.text

        manager = login(owner.email, "task-passwort-123")
        mine = manager.get("/kalender/buchungen")
        assert "Erika Geheim" not in mine.text
        team = manager.get("/kalender/buchungen?scope=team")
        assert team.status_code == 200
        assert "Erika Geheim" not in team.text
        assert "Bürgertermin (belegt)" in team.text

        page.integration_json = json.dumps({"calendar_privacy": "staff"})
        db.commit()
        authorized = manager.get("/kalender/buchungen?scope=team&status=requested")
        assert "Erika Geheim" in authorized.text
        confirmed = manager.get("/kalender/buchungen?scope=team&status=booked")
        assert "Erika Geheim" not in confirmed.text

        # The team filter must not allow an outsider to infer citizen identity.
        rejected = without_role.get(
            f"/kalender/buchungen?scope=team&page={page.id}&q=Erika")
        assert rejected.status_code == 200
        assert "Erika Geheim" not in rejected.text
    finally:
        db.delete(booking)
        db.delete(page)
        db.commit()
        settings(module_bookings=old.get("module_bookings", "1"),
                 module_calendars=old.get("module_calendars", "0"))
