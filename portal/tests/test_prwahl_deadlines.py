"""Advisory calendar calculations for the standard RLP staff council election."""
from datetime import date, timedelta
from types import SimpleNamespace
from app.prwahl_deadlines import suggestions


def election(start, end=None, body="personalrat"):
    return SimpleNamespace(election_day=start, election_end_day=end, body_type=body)


def test_notice_latest_date_is_six_weeks_before_last_voting_day():
    items = suggestions(election(date(2027, 4, 13), date(2027, 4, 14)))
    notice = next(item for item in items if item["code"] == "notice")
    assert notice["on"] == date(2027, 4, 14) - timedelta(days=42)
    assert "§ 6" in notice["rule"]
    assert "§ 4" in notice["detail"]


def test_nomination_requires_actual_announcement_date_and_warns_about_exceptions():
    no_notice = suggestions(election(date(2027, 4, 14)))
    assert not any(item["code"] == "nominations" for item in no_notice)
    with_notice = suggestions(election(date(2027, 4, 14)), notice_effective_on=date(2027, 2, 25))
    deadline = next(item for item in with_notice if item["code"] == "nominations")
    assert deadline["on"] == date(2027, 3, 15)
    assert "Verschiebung" in deadline["detail"]


def test_no_unreviewed_legal_deadline_for_other_election_bodies():
    items = suggestions(election(date(2027, 5, 20), body="jav"))
    assert [i["code"] for i in items] == ["vote"]


def test_missing_dates_generate_no_fabricated_deadline():
    assert suggestions(election(None)) == []
    assert suggestions(election(date(2027, 5, 20), date(2027, 5, 19))) == []
