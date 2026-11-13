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


def test_notice_date_after_latest_standard_window_is_flagged():
    from app.prwahl_deadlines import diagnose
    warnings = diagnose(election(date(2027, 4, 14)), notice_effective_on=date(2027, 3, 10))
    assert any("Sechswochen" in w["title"] for w in warnings)
    assert any("Vorschlagsfrist" in w["title"] for w in warnings)
    assert all(w["kind"] == "warning" for w in warnings)


def test_missing_notice_is_explicit_not_assumed_and_special_body_is_not_calculated():
    from app.prwahl_deadlines import diagnose
    assert any("nicht dokumentiert" in w["title"] for w in diagnose(election(date(2027, 4, 14))))
    special = diagnose(election(date(2027, 4, 14), body="gesamtpersonalrat"))
    assert len(special) == 1 and special[0]["kind"] == "info"


def test_existing_calendar_event_marks_local_day_without_inventing_new_event():
    from datetime import datetime
    from types import SimpleNamespace
    from app.prwahl_deadlines import mark_existing
    rows = suggestions(election(date(2027, 4, 14)))
    # 07:00 UTC on 14 April is 09:00 local Berlin time.
    event = SimpleNamespace(kind="ballot", starts_at=datetime(2027, 4, 14, 7), status="planned")
    marked = mark_existing(rows, [event])
    assert next(r for r in marked if r["code"] == "vote")["already_planned"] is True
    assert next(r for r in marked if r["code"] == "notice")["already_planned"] is False
    event.status = "cancelled"
    assert not any(r["already_planned"] for r in mark_existing(rows, [event]))
