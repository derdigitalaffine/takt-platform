"""Conservative election document prefill never invents legal determinations."""
from datetime import date, datetime
from types import SimpleNamespace
from app.prwahl_prefill import prefill_fields


def _election():
    return SimpleNamespace(title="Personalratswahl Muster", election_day=date(2027, 4, 14),
                           election_location="Rathaus", service_name="Stadtverwaltung")


def test_prefill_known_date_and_location_but_not_deadlines_or_seats():
    values, sources = prefill_fields(_election(), "election_notice")
    assert "14.04.2027" in values["voting"] and "Rathaus" in values["voting"]
    assert "Planungsdaten" in sources["voting"]
    assert "objections" not in values
    assert "nominations" not in values
    assert "seats" not in values
    assert "election_mode" not in values


def test_prefill_scoped_mandates_without_inventing_attendance():
    chair = SimpleNamespace(role="chair", appointment_reference="Beschluss Muster")
    person = SimpleNamespace(name="Lena Beispiel", active=True)
    values, sources = prefill_fields(_election(), "board_notice", mandates=[(chair, person)])
    assert "Lena Beispiel" in values["board_members"]
    assert "Beschluss Muster" in values["reference"]
    assert "prüfen" in sources["board_members"]
    minutes, _ = prefill_fields(_election(), "board_minutes", mandates=[(chair, person)])
    assert "attendance" not in minutes  # A role never proves actual attendance.
    assert "session" not in minutes  # No completed meeting is documented.


def test_prefill_only_confirmed_aggregated_paper_counts():
    draft = SimpleNamespace(group_name="Gruppe A", status="draft", ballots_cast=35, invalid_ballots=2)
    confirmed = SimpleNamespace(group_name="Gruppe B", status="confirmed", ballots_cast=90, invalid_ballots=4)
    values, sources = prefill_fields(_election(), "count_protocol", rounds=[draft, confirmed])
    assert "90 Stimmzettel" in values["ballots"]
    assert "35" not in values["ballots"]
    assert "amtliche" in sources["ballots"]
    assert "resolution" not in values


def test_prefill_fills_planned_count_event_without_legal_confirmation():
    event = SimpleNamespace(kind="count", status="planned", location="Sitzungssaal",
                            starts_at=datetime(2027, 4, 14, 15, 0))
    values, sources = prefill_fields(_election(), "election_notice", events=[event])
    assert "Sitzungssaal" in values["counting"]
    assert "Geplanter" in sources["counting"]


def test_planned_constitution_does_not_fill_minutes_with_unverified_meeting():
    appointment = SimpleNamespace(kind="constitution", status="planned", location="Rathaus",
                                  starts_at=datetime(2027, 5, 1, 10, 0))
    draft, _ = prefill_fields(_election(), "constitution_minutes", events=[appointment])
    assert "meeting" not in draft
    invite, source = prefill_fields(_election(), "constitution_invitation", events=[appointment])
    assert "Rathaus" in invite["meeting"]
    assert "Geplanter" in source["meeting"]
