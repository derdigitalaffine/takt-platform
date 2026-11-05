from datetime import date
import pytest
from app.staffing import Period, Rule, ancestors, check_headcount


def test_half_days_ancestor_dedup_and_forecast_do_not_reserve():
    day = date(2026, 3, 30)
    rows = [(1, 3, True), (1, 2, True), (2, 3, True), (3, 2, True), (4, 3, False)]
    conflicts = check_headcount(
        candidate=Period(1, day, day, "pm", "pm"),
        memberships=rows,
        parents={1: None, 2: 1, 3: 2},
        rules=[Rule(2, 2, "block"), Rule(3, 2, "warning")],
        unavailable=[],
        tentative=[Period(2, day, day)],
    )
    assert [(c.org_id, c.half, c.available, c.forecast) for c in conflicts] == [
        (2, "pm", 1, True),
        (3, "pm", 1, False),
        (3, "pm", 0, True),
    ]


def test_effective_absences_and_working_half_day():
    day = date(2026, 10, 26)
    result = check_headcount(
        candidate=Period(1, day, day),
        memberships=[(1, 1, True), (2, 1, True), (3, 1, True)],
        parents={1: None},
        rules=[Rule(1, 2, "block")],
        unavailable=[Period(2, day, day, "am", "am")],
        working={
            1: {(day, "am"), (day, "pm")},
            2: {(day, "am"), (day, "pm")},
            3: {(day, "pm")},
        },
    )
    assert [(c.half, c.available) for c in result] == [("am", 0)]


def test_invalid_period_and_hierarchy_are_rejected():
    day = date(2026, 1, 1)
    with pytest.raises(ValueError):
        Period(1, day, day, "pm", "am")
    with pytest.raises(ValueError):
        ancestors(1, {1: 2, 2: 1})
    with pytest.raises(ValueError):
        ancestors(1, {1: 2})


def test_closed_nonworking_half_is_not_a_staffing_shortfall():
    day = date(2026, 12, 5)
    assert (
        check_headcount(
            candidate=Period(1, day, day),
            memberships=[(1, 1, True)],
            parents={1: None},
            rules=[Rule(1, 1, "block")],
            unavailable=[],
            working={1: set()},
        )
        == []
    )
