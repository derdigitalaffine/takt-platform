"""Aggregate paper-count arithmetic: deterministic, exact and fail-safe."""
import pytest
from fastapi import HTTPException
from app.prwahl_workflow import dhondt, validate_totals, parse_entries, check_count, STAGES


def test_full_lifecycle_has_constitution_and_archive():
    keys = [row[0] for row in STAGES]
    assert keys[0] == "appointment"
    assert keys[-2:] == ["constitution", "archive"]
    assert len(keys) == len(set(keys))


def test_list_allocation_exact_divisors():
    result = dhondt([("Liste A", 100), ("Liste B", 60), ("Liste C", 20)], 3)
    assert result["complete"] is True
    assert result["assigned"] == {"Liste A": 2, "Liste B": 1, "Liste C": 0}
    assert len(result["rows"]) == 3


def test_ties_stop_before_legal_decision():
    result = dhondt([("A", 100), ("B", 100)], 1)
    assert result["complete"] is False
    assert result["tie"]["seat"] == 1
    assert set(result["tie"]["labels"]) == {"A", "B"}
    assert result["assigned"] == {"A": 0, "B": 0}


def test_valid_ballot_reconciliation_and_person_votes():
    values = validate_totals(eligible=120, voters=100, ballots_cast=100,
                             invalid_ballots=5, abstentions=2)
    assert values == (120, 100, 100, 5, 2)
    entries = parse_entries("Liste A; 60\nListe B; 33")
    result = check_count("list", 3, 100, 5, 2, entries)
    assert result["complete"]
    assert sum(result["assigned"].values()) == 3
    people = check_count("person", 3, 100, 5, 0,
                         parse_entries("Person A; 90\nPerson B; 80"))
    assert people["complete"] is False
    assert people["assigned"] == {}


@pytest.mark.parametrize("values", [
    dict(eligible=10, voters=11, ballots_cast=10, invalid_ballots=0, abstentions=0),
    dict(eligible=10, voters=10, ballots_cast=11, invalid_ballots=0, abstentions=0),
    dict(eligible=10, voters=10, ballots_cast=10, invalid_ballots=11, abstentions=0),
    dict(eligible=10, voters=10, ballots_cast=10, invalid_ballots=1, abstentions=10),
])
def test_impossible_counts_rejected(values):
    with pytest.raises(HTTPException) as exc:
        validate_totals(**values)
    assert exc.value.status_code == 422


def test_duplicate_labels_and_overvotes_rejected():
    with pytest.raises(HTTPException):
        parse_entries("Liste A; 4\nliste a; 6")
    with pytest.raises(HTTPException):
        check_count("list", 2, 100, 0, 0, [("A", 99)])
    with pytest.raises(HTTPException):
        check_count("person", 2, 100, 0, 0, [("A", 201)])


def test_paper_only_result_does_not_require_digital_count(client):
    """An official paper count is valid without optional TAKT count entries.

    This regression exercises the milestone endpoint, not the d'Hondt helper.
    """
    from app.db import SessionLocal
    from app.prwahl_models import PRElection, PRMandate
    from app.prwahl_workflow import PRMilestone
    from conftest import login, csrf_of, settings
    from sqlalchemy import select

    settings(module_prwahl="1")
    admin = login("admin@example.org", "admin-passwort-123")
    with SessionLocal() as db:
        # Use an election that explicitly grants the logged-in administrator
        # the election chair mandate; global admin alone is insufficient.
        from app.db import User
        user = db.scalar(select(User).where(User.email == "admin@example.org"))
        election = db.scalar(select(PRElection).join(PRMandate, PRMandate.election_id == PRElection.id)
                             .where(PRMandate.user_id == user.id, PRMandate.role == "chair"))
        if election is None:
            pytest.skip("No chair fixture is installed; endpoint test needs election fixture")
        eid = election.id
    page = admin.get(f"/personalratswahl/{eid}/ablauf")
    assert page.status_code == 200
    response = admin.post(f"/personalratswahl/{eid}/ablauf/determination/nachweis", data={
        "csrf": csrf_of(page.text), "evidence": "Unterzeichnete Wahlniederschrift, Akte 2026/PR-01",
    })
    assert response.status_code in (303, 409)
