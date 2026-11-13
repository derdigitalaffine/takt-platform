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


@pytest.mark.parametrize("entries", [
    [("A", 10), ("a", 5)],
    [(" A ", 10), ("a", 5)],
    [("", 10)],
    [("A", -1)],
    [("A", True)],
    [("A", "10")],
])
def test_direct_dhondt_rejects_malformed_entries(entries):
    with pytest.raises(HTTPException) as exc:
        dhondt(entries, 2)
    assert exc.value.status_code == 422


def test_dhondt_zero_votes_are_rejected():
    with pytest.raises(HTTPException) as exc:
        dhondt([("A", 0), ("B", 0)], 1)
    assert exc.value.status_code == 422
