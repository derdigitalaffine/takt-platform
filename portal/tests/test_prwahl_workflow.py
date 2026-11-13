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


@pytest.mark.parametrize("bad", [True, False, 1.9, -0.1, "1.5", "NaN", "", "  ", "1e2"])
def test_ballot_totals_reject_non_integer_inputs(bad):
    with pytest.raises(HTTPException) as exc:
        validate_totals(eligible=bad, voters=0, ballots_cast=0,
                        invalid_ballots=0, abstentions=0)
    assert exc.value.status_code == 422


def test_ballot_totals_accept_decimal_string_from_html_form():
    assert validate_totals(eligible="120", voters="100", ballots_cast="99",
                           invalid_ballots="4", abstentions="0") == (120, 100, 99, 4, 0)


@pytest.mark.parametrize("entries", [
    [("A", 10000001)],
    [("A", 1), ("A ", 2)],
    [("A", 1), ("B", 2, 3)],
    [("A", 1), ("B",)],
    [("A", 1), "B"],
    [("A", 1)] * 151,
])
def test_direct_allocation_rejects_invalid_structure_or_bounds(entries):
    with pytest.raises(HTTPException) as exc:
        dhondt(entries, 2)
    assert exc.value.status_code == 422


def test_direct_allocation_normalizes_surrounding_whitespace():
    result = dhondt([(" Liste A ", 100), ("Liste B", 60)], 1)
    assert result["complete"] is True
    assert result["assigned"] == {"Liste A": 1, "Liste B": 0}


@pytest.mark.parametrize("entries", [
    [("Person A", -1)],
    [("Person A", True)],
    [("Person A", "3")],
    [("Person A", 2), ("person a", 3)],
    [("Person A", 2), (" Person A ", 3)],
    [("Person A", 2, 3)],
    [],
])
def test_person_count_rejects_malformed_direct_entries(entries):
    with pytest.raises(HTTPException) as exc:
        check_count("person", 2, 10, 0, 0, entries)
    assert exc.value.status_code == 422


@pytest.mark.parametrize("ballots,invalid,abstain", [
    (10, 11, 0), (10, -1, 0), (10, 0, 11),
    (True, 0, 0), (10.5, 0, 0), (10, 0, -1),
])
def test_direct_count_rejects_invalid_ballot_totals(ballots, invalid, abstain):
    with pytest.raises(HTTPException) as exc:
        check_count("person", 2, ballots, invalid, abstain, [("Person A", 1)])
    assert exc.value.status_code == 422


def test_person_count_does_not_count_abstentions_as_vote_capacity():
    with pytest.raises(HTTPException) as exc:
        check_count("person", 2, 10, 0, 5, [("Person A", 11)])
    assert exc.value.status_code == 422
