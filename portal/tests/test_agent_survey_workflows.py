"""Survey engine integration: native drafts, explicit lifecycle and live object rights."""

import json
import pytest
from fastapi import HTTPException
from sqlalchemy import select, delete
from app import agent, agent_surveys, shares, live
from app.db import (
    SessionLocal,
    User,
    Poll,
    Vote,
    LivePoll,
    PollShare,
    get_settings,
    set_setting,
)
from app.ai_models import AgentAudit
from app.security import new_link_token
from test_agent_modules import isolated, ADMIN, fake, plan
from test_agent_drafts import final_tokens
from test_agent import _member
from conftest import settings, login, csrf_of


@pytest.fixture(autouse=True)
def survey_on(isolated):
    with SessionLocal() as db:
        old = get_settings(db).get("module_polls", "0")
        before = {m: set(db.scalars(select(m.id))) for m in (Poll, Vote, LivePoll)}
    settings(module_polls="1")
    yield
    with SessionLocal() as db:
        for m in (Poll, Vote, LivePoll):
            for row in db.scalars(select(m).where(m.id.not_in(before[m]))):
                db.delete(row)
        set_setting(db, "module_polls", old)
        db.commit()
    from app import main

    main._module_cache["at"] = 0


def raw(kind):
    value = dict(
        tool="create_survey",
        record_kind=kind,
        title="Agent " + kind,
        description="Konkrete Vorbereitung",
    )
    if kind == "poll":
        value.update(
            duration=60,
            location="Raum 2",
            options=[
                dict(date="2030-12-05", start="09:00", end="10:00"),
                dict(date="2030-12-06", start="09:00", end="10:00"),
            ],
        )
    elif kind == "vote":
        value.update(
            secrecy="anonymous",
            access=["public"],
            results="live",
            questions=[dict(title="Welche Option?", kind="single", options=["A", "B"])],
        )
    else:
        value.update(
            pacing="free",
            questions=[
                dict(title="Wie geht es dir?", kind="scale", min=1, max=5),
                dict(title="Ein Begriff?", kind="words"),
            ],
        )
    return value


def normalize(db, actor, value, found=None):
    return agent.normalize_plan(
        json.dumps(dict(actions=[value])), actor, found or [], [], db
    )["actions"][0]


@pytest.mark.parametrize("kind", ["poll", "vote", "live_poll"])
def test_all_families_are_concrete_closed_drafts_and_audited(kind):
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        action = normalize(db, actor, raw(kind))
        model = agent_surveys.MODELS[kind]
        assert not db.scalar(select(model).where(model.title == action["title"]))
        preview = agent.preview(db, [action])[0]
        assert "Entwurf" in preview and (
            "2030-12-05" in preview
            if kind == "poll"
            else (
                "Wie geht es dir?" in preview
                if kind == "live_poll"
                else "Anonym" in preview
            )
        )
        rid = agent.execute(db, actor, [action])[0]["target_id"]
        row = db.get(model, rid)
        if kind == "poll":
            assert (
                row.closed
                and row.published_at is None
                and row.public_token is None
                and len(row.options) == 2
            )
        else:
            assert row.status == "draft" and row.opened_at is None and row.questions
            if kind == "vote":
                assert row.secrecy == "anonymous" and row.access == "public"
            else:
                assert (
                    row.pacing == "free"
                    and live.settings(row.questions[0])["max"] == 5
                    and live.settings(row.questions[1])["filter"]
                )
        assert db.scalar(
            select(AgentAudit).where(
                AgentAudit.tool == "create_survey", AgentAudit.target_id == rid
            )
        )


def test_poll_native_edits_publish_and_final_option_require_fresh_confirmation(
    monkeypatch,
):
    c = login(*ADMIN)
    fake(monkeypatch, [], [raw("poll")])
    response, csrf = plan(c, "Erstelle eine Terminumfrage")
    assert response.status_code == 200, response.text
    pid = response.json()["plan_id"]
    assert response.json()["open_url"].startswith("/polls/new?agent_plan=")
    assert c.get(response.json()["open_url"]).status_code == 200
    assert c.post("/agent/draft/review", data=dict(agent_plan=pid)).status_code == 400
    options = [dict(date="2030-12-09", start="11:00", end="12:00")]
    review = c.post(
        "/agent/draft/review",
        data=dict(
            csrf=csrf,
            agent_plan=pid,
            title="Manuell geprüft",
            description="Geprüfte Beschreibung",
            duration="90",
            location="Raum 3",
            options_json=json.dumps(options),
        ),
    )
    assert (
        review.status_code == 200
        and "2030-12-09" in review.text
        and "90 Minuten" in review.text
    )
    saved = c.post("/agent/draft/save", data=final_tokens(review.text))
    assert saved.status_code == 303
    with SessionLocal() as db:
        row = db.scalar(select(Poll).where(Poll.title == "Manuell geprüft"))
        rid = row.id
        oid = row.options[0].id
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        found = agent.search(
            db, actor, dict(tool="search_surveys", query="Manuell geprüft")
        )
        assert any(r["type"] == "poll_option" and r["id"] == oid for r in found)
        publish = normalize(
            db,
            actor,
            dict(tool="survey_state", record_kind="poll", id=rid, operation="publish"),
            found,
        )
        assert (
            "öffentlichen Teilnahmelink" in agent.preview(db, [publish])[0]
            and row.public_token is None
        )
        agent.execute(db, actor, [publish])
        db.refresh(row)
        assert not row.closed and row.public_token
        found = agent.search(
            db, actor, dict(tool="search_surveys", query="Manuell geprüft")
        )
        final = normalize(
            db,
            actor,
            dict(tool="finalize_poll", id=rid, option_id=oid, notify=False),
            found,
        )
        assert row.final_option_id is None
        agent.execute(db, actor, [final])
        db.refresh(row)
        assert row.final_option_id == oid and row.closed and row.used_at


def test_live_record_rights_and_stale_proposal_are_enforced():
    uid = _member("agent-survey-reader@example.org")
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        reader = db.get(User, uid)
        rid = agent.execute(db, actor, [normalize(db, actor, raw("poll"))])[0][
            "target_id"
        ]
        row = db.get(Poll, rid)
        assert (
            agent.search(db, reader, dict(tool="search_surveys", query="Agent poll"))
            == []
        )
        db.add(PollShare(poll_id=rid, user_id=uid, level=shares.VIEW))
        db.commit()
        found = agent.search(
            db, reader, dict(tool="search_surveys", query="Agent poll")
        )
        assert found[0]["operations"] == []
        with pytest.raises(HTTPException):
            normalize(
                db,
                reader,
                dict(
                    tool="survey_state", record_kind="poll", id=rid, operation="publish"
                ),
                found,
            )
        ownerfound = agent.search(
            db, actor, dict(tool="search_surveys", query="Agent poll")
        )
        change = normalize(
            db,
            actor,
            dict(tool="survey_state", record_kind="poll", id=rid, operation="publish"),
            ownerfound,
        )
        row.title = "Zwischenzeitlich geändert"
        db.commit()
        with pytest.raises(HTTPException) as exc:
            agent.execute(db, actor, [change])
        assert exc.value.status_code == 409
        db.rollback()
        with pytest.raises(HTTPException):
            normalize(db, reader, raw("vote"))
        settings(module_polls="0")
        with pytest.raises(HTTPException):
            agent.search(db, actor, dict(tool="search_surveys", query=""))


def test_vote_freezes_results_and_live_retains_native_moderation():
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        for kind in ("vote", "live_poll"):
            rid = agent.execute(db, actor, [normalize(db, actor, raw(kind))])[0][
                "target_id"
            ]
            findings = agent.search(
                db, actor, dict(tool="search_surveys", query="Agent " + kind)
            )
            op = "start" if kind == "vote" else "open"
            start = normalize(
                db,
                actor,
                dict(tool="survey_state", record_kind=kind, id=rid, operation=op),
                findings,
            )
            agent.execute(db, actor, [start])
            row = db.get(agent_surveys.MODELS[kind], rid)
            assert row.status == "open" and row.opened_at
            findings = agent.search(
                db, actor, dict(tool="search_surveys", query="Agent " + kind)
            )
            stop = normalize(
                db,
                actor,
                dict(tool="survey_state", record_kind=kind, id=rid, operation="close"),
                findings,
            )
            agent.execute(db, actor, [stop])
            db.refresh(row)
            assert row.status == "closed"
            if kind == "vote":
                assert row.result_hash and row.result_json
                with pytest.raises(HTTPException):
                    normalize(
                        db,
                        actor,
                        dict(
                            tool="survey_state",
                            record_kind=kind,
                            id=rid,
                            operation="start",
                        ),
                        findings,
                    )


@pytest.mark.parametrize(
    "bad",
    [
        dict(
            record_kind="poll",
            options=[dict(date="2030-12-05", start="11:00", end="10:00")],
        ),
        dict(
            record_kind="vote",
            questions=[dict(title="Ungültig", kind="not-real", options=["A", "B"])],
        ),
        dict(
            record_kind="live_poll",
            questions=[dict(title="Nicht klemmen", kind="scale", min=1, max=100)],
        ),
    ],
)
def test_invalid_settings_fail_before_any_draft(bad):
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        value = raw(bad["record_kind"])
        value.update(bad)
        with pytest.raises((ValueError, HTTPException)):
            normalize(db, actor, value)


def test_quiz_and_slider_preserve_exact_native_settings_and_question_types():
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == ADMIN[0]))
        value = raw("live_poll")
        value["questions"] = [
            dict(
                title="Welche Zahl ist gerade?",
                kind="quiz",
                options=["Zwei", "Drei"],
                correct=[1],
                points=7,
                seconds=40,
                partial=True,
                nickname=True,
            ),
            dict(
                title="Dein Wert?", kind="slider", min=-5, max=15, step=2, unit="Punkte"
            ),
        ]
        action = normalize(db, actor, value)
        preview = agent.preview(db, [action])[0]
        assert (
            "Richtige Lösung: Zwei" in preview
            and "Punkte 7" in preview
            and "40 Sekunden" in preview
        )
        rid = agent.execute(db, actor, [action])[0]["target_id"]
        row = db.get(LivePoll, rid)
        quiz, slider = row.questions
        quiz_settings = live.settings(quiz)
        assert (
            quiz_settings["correct"] == [live.opts(quiz)[0]["id"]]
            and quiz_settings["points"] == 7
            and quiz_settings["seconds"] == 40
            and quiz_settings["partial"]
            and quiz_settings["nickname"]
        )
        assert {
            k: live.settings(slider)[k] for k in ("min", "max", "step", "unit")
        } == dict(min=-5, max=15, step=2, unit="Punkte")


def test_small_model_contract_separates_date_polls_from_free_calendar_events():
    from app.agent_precision import focus_modules, context

    focus = focus_modules("Erstelle eine Terminumfrage mit zwei Terminen")
    assert "surveys" in focus and "calendars" not in focus
    assert "calendars" in focus_modules(
        "Erstelle eine Terminumfrage und einen Kalendereintrag"
    )
    assert "record_kind=poll" in context("Erstelle eine Terminumfrage", [])
