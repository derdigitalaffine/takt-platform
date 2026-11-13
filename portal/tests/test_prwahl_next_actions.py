"""The election dashboard recommends only authorized, non-binding next steps."""
from datetime import date
from types import SimpleNamespace
from app.prwahl_next_actions import next_actions


def election(*, election_day=None, gate="pending"):
    return SimpleNamespace(id=42, legal_gate=gate, election_day=election_day)


def test_actions_are_scoped_to_missing_work_and_prioritized():
    actions = next_actions(election(), "coordinator", [], [], [], set())
    codes = [a["code"] for a in actions]
    assert codes == ["legal", "chair", "date", "notice_draft", "dates"]
    assert actions[1]["href"] == "/personalratswahl/42?tab=board"
    assert actions[2]["href"].endswith("#pr-data-form")
    assert all("rechtswirksam" not in a["title"].lower() for a in actions)


def test_actions_disappear_when_preparations_are_documented():
    chair = (SimpleNamespace(role="chair"), SimpleNamespace(name="Muster"))
    notice = SimpleNamespace(kind="election_notice")
    actions = next_actions(election(election_day=date(2027, 4, 14), gate="approved"),
                           "chair", [chair], [notice], [123], {"announcement"})
    assert actions == []


def test_read_only_roles_never_receive_mutating_navigation():
    actions = next_actions(election(election_day=date(2027, 4, 14)),
                           "auditor", [], [], [], set())
    assert actions
    assert all(a["href"] == "" for a in actions)
