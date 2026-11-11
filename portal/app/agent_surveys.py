"""Survey metadata and closed drafts. Never read individual ballots or answer text for an LLM."""

import hashlib
import json
import re
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, func
from . import (
    surveys,
    shares,
    polls,
    votes,
    live,
    survey_commands as commands,
    poll_lifecycle as lifecycle,
)
from .db import Poll, Vote, LivePoll, LiveQuestion, PollOption, VoteBallot, LiveAnswer
from .security import new_link_token

TOOLS = {"create_survey", "survey_state", "finalize_poll"}
MODELS = {"poll": Poll, "vote": Vote, "live_poll": LivePoll}
LABELS = {"poll": "Terminumfrage", "vote": "Abstimmung", "live_poll": "Live-Umfrage"}


def require(user):
    from .agent import require as module_access

    module_access(user, "surveys")


def revision(db, kind, row):
    if not row:
        return None
    values = [
        getattr(row, k, None)
        for k in (
            "title",
            "description",
            "owner_id",
            "updated_at",
            "archived_at",
            "status",
            "closed",
            "published_at",
            "expires_at",
            "ends_at",
            "final_option_id",
            "secrecy",
            "access",
            "results",
            "current_id",
            "pacing",
        )
    ]
    if kind == "poll":
        values += [(o.id, o.starts_at, o.ends_at, o.note) for o in row.options]
        values += [(p.id, p.answered_at) for p in row.participants]
    else:
        values += [
            (q.id, q.title, q.kind, q.options_json, getattr(q, "settings_json", ""))
            for q in row.questions
        ]
        model, column = (
            (VoteBallot, VoteBallot.vote_id)
            if kind == "vote"
            else (LiveAnswer, LiveAnswer.poll_id)
        )
        values += [
            db.scalar(select(func.count()).select_from(model).where(column == row.id))
        ]
        if kind == "vote":
            values += [(v.id, v.invited_at, v.source) for v in row.voters]
    return hashlib.sha256(json.dumps(values, default=str).encode()).hexdigest()


def target(db, user, action):
    require(user)
    kind = action["record_kind"]
    row = db.get(MODELS[kind], action["id"])
    if commands.level(db, user, kind, row) < shares.VIEW:
        raise HTTPException(404, "Umfrage nicht gefunden.")
    lifecycle.mutable(row)
    if revision(db, kind, row) != action["version"]:
        raise HTTPException(409, "Umfrage oder Beteiligung geändert. Bitte neu planen.")
    if action["tool"] == "survey_state":
        commands.validate_state(db, user, kind, row, action["operation"])
    elif commands.level(db, user, kind, row) < shares.EDIT:
        raise HTTPException(403)
    return row


def operations(db, user, kind, row):
    choices = {
        "poll": ("publish", "reopen", "close"),
        "vote": ("start", "pause", "close"),
        "live_poll": ("open", "close"),
    }[kind]
    allowed = []
    for op in choices:
        if kind == "poll" and (
            (op == "publish" and row.published_at)
            or (op == "reopen" and (not row.closed or not row.published_at))
            or (op == "close" and row.closed)
        ):
            continue
        if (
            kind == "vote"
            and op == "close"
            and (not row.opened_at or commands.level(db, user, kind, row) < shares.EDIT)
        ):
            continue
        if kind != "poll" and (
            (op in ("open", "start") and row.status == "open")
            or (op == "close" and row.status == "closed")
        ):
            continue
        try:
            commands.validate_state(db, user, kind, row, op)
        except HTTPException:
            continue
        allowed.append(op)
    return allowed


def search(db, user, spec):
    from .main import enabled_modules

    require(user)
    phrase = str(spec.get("query") or "").strip()[:100]
    out = []
    for item in surveys.collect(db, user, enabled_modules()):
        if phrase.lstrip("#").isdigit():
            if item["id"] != int(phrase.lstrip("#")):
                continue
        elif phrase.casefold() not in item["title"].casefold():
            continue
        kind = "live_poll" if item["kind"] == "live" else item["kind"]
        row = db.get(MODELS[kind], item["id"])
        out.append(
            dict(
                type=kind,
                id=row.id,
                title=row.title,
                status=item["status"],
                questions=item["question_count"],
                response_count=item["count"],
                operations=operations(db, user, kind, row),
                url=item["href"],
            )
        )
        if kind == "poll" and phrase:
            for option in row.options[:20]:
                out.append(
                    dict(
                        type="poll_option",
                        id=option.id,
                        poll_id=row.id,
                        title=polls.option_parts(option)["label"],
                        url=f"/polls/{row.id}",
                    )
                )
                if len(out) >= 50:
                    break
        if len(out) >= 50:
            break
    return out[:50]


def _text(raw, key, limit, required=False):
    value = raw.get(key, "")
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (required and not value.strip())
    ):
        raise ValueError(
            "Bitte gültige Angaben für "
            + {
                "title": "Titel",
                "description": "Beschreibung",
                "location": "Ort",
                "date": "Datum",
                "start": "Beginn",
                "end": "Ende",
                "note": "Notiz",
            }.get(key, key)
            + " angeben."
        )
    return value.strip()


def live_payload(question):
    value = dict(question, options="\n".join(question.get("options", [])))
    for key in ("approve", "filter", "partial", "nickname"):
        if key in value:
            value[key] = "1" if value[key] else "0"
    if isinstance(value.get("correct"), list):
        value["correct"] = ",".join(map(str, value["correct"]))
    return value


def draft(user, raw):
    from .planning import DURATIONS

    require(user)
    kind = raw.get("record_kind")
    if kind not in MODELS:
        raise ValueError("Bitte Terminumfrage, Abstimmung oder Live-Umfrage wählen.")
    if not user.can("polls" if kind == "poll" else "votes"):
        raise HTTPException(403)
    action = dict(
        tool="create_survey",
        record_kind=kind,
        title=" ".join(_text(raw, "title", 255, True).split()),
        description=_text(raw, "description", 2000 if kind == "live_poll" else 5000),
    )
    if kind == "poll":
        from .agent_events import local_timestamp
        from .db import LOCAL_TZ

        options = raw.get("options")
        if not isinstance(options, list) or not 1 <= len(options) <= 100:
            raise ValueError("1 bis 100 konkrete Terminvorschläge angeben.")
        clean = []
        for item in options:
            if not isinstance(item, dict):
                raise ValueError("Ungültiger Terminvorschlag.")
            day = _text(item, "date", 10, True)
            try:
                parsed = date.fromisoformat(day)
                if len(day) != 10 or not 1970 <= parsed.year <= 2200:
                    raise ValueError()
            except ValueError:
                raise ValueError("Terminvorschlag als YYYY-MM-DD angeben.")
            start, end = _text(item, "start", 5), _text(item, "end", 5)
            if end and not start:
                raise ValueError("Ein Ende benötigt eine Startzeit.")
            if start:
                a = local_timestamp(day, start, str(LOCAL_TZ))
                if end:
                    b = local_timestamp(day, end, str(LOCAL_TZ))
                    if b <= a:
                        raise ValueError("Das Ende muss nach der Startzeit liegen.")
            clean.append(
                dict(date=day, start=start, end=end, note=_text(item, "note", 120))
            )
        parsed = polls.parse_options(json.dumps(clean))
        if len(parsed) != len(clean):
            raise ValueError("Ungültige oder doppelte Terminvorschläge.")
        duration = raw.get("duration", 60)
        if type(duration) is not int or duration not in DURATIONS:
            raise ValueError(
                "Eine angebotene Dauer wählen: " + ", ".join(map(str, DURATIONS))
            )
        action.update(
            options=clean, duration=duration, location=_text(raw, "location", 255)
        )
    else:
        if kind == "vote":
            secrecy = raw.get("secrecy", "secret")
            access = raw.get("access", ["invite"])
            results = raw.get("results", "after_end")
            if (
                secrecy not in votes.SECRECY
                or results not in votes.RESULTS
                or not isinstance(access, list)
                or not access
                or len(access) != len(set(access))
                or any(v not in votes.ACCESS for v in access)
            ):
                raise ValueError(
                    "Geheimhaltung, Zugang und Ergebnissichtbarkeit prüfen."
                )
            change = raw.get("allow_change", False)
            if type(change) is not bool or (change and secrecy != "open"):
                raise ValueError("Stimmen sind nur bei offener Abstimmung änderbar.")
            action.update(
                secrecy=secrecy, access=access, results=results, allow_change=change
            )
        else:
            pacing = raw.get("pacing", "moderated")
            if pacing not in live.PACING:
                raise ValueError("Moderierten oder freien Live-Ablauf wählen.")
            action["pacing"] = pacing
        questions = raw.get("questions")
        if not isinstance(questions, list) or not 1 <= len(questions) <= 30:
            raise ValueError("1 bis 30 konkrete Fragen angeben.")
        clean = []
        for item in questions:
            if not isinstance(item, dict):
                raise ValueError("Ungültige Umfragefrage.")
            title = _text(item, "title", 500, True)
            qkind = item.get("kind", "single")
            if kind == "vote":
                if qkind not in votes.KINDS:
                    raise ValueError("Unbekannter Abstimmungsfragetyp.")
                opts = item.get("options")
                if not isinstance(opts, list) or not 2 <= len(opts) <= 50:
                    raise ValueError("2 bis 50 konkrete Antwortmöglichkeiten angeben.")
                labels = [
                    (
                        o
                        if isinstance(o, str)
                        else o.get("label") if isinstance(o, dict) else None
                    )
                    for o in opts
                ]
                if any(
                    not isinstance(v, str) or not v.strip() or len(v) > 300
                    for v in labels
                ):
                    raise ValueError("Antwortbezeichnungen prüfen.")
                question = dict(
                    title=title,
                    kind=qkind,
                    options=[
                        dict(id="o" + str(i), label=v.strip())
                        for i, v in enumerate(labels)
                    ],
                    min=item.get("min", 0 if qkind == "multi" else 1),
                    max=item.get("max", 1 if qkind == "single" else len(labels)),
                    points=item.get("points", 10),
                    abstain=item.get("abstain", True),
                )
                if (
                    type(question["min"]) is not int
                    or type(question["max"]) is not int
                    or not 0 <= question["min"] <= question["max"] <= len(labels)
                    or question["max"] < 1
                    or type(question["points"]) is not int
                    or not 1 <= question["points"] <= 1000
                    or type(question["abstain"]) is not bool
                ):
                    raise ValueError("Auswahlgrenzen, Punkte oder Enthaltung prüfen.")
                if qkind == "single" and (question["min"] != 1 or question["max"] != 1):
                    raise ValueError("Einfachauswahl erlaubt genau eine Antwort.")
                clean.append(question)
            else:
                if qkind not in live.KINDS:
                    raise ValueError(
                        "Diesen Live-Fragetyp bitte im nativen Editor ergänzen."
                    )
                opts = item.get("options", [])
                if not isinstance(opts, list):
                    raise ValueError("Antwortoptionen als Liste angeben.")
                if qkind not in ("single", "multi", "rank", "quiz") and opts:
                    raise ValueError(
                        "Dieser Live-Fragetyp hat keine frei benannten Antwortoptionen."
                    )
                if qkind in ("single", "multi", "rank", "quiz") and (
                    not isinstance(opts, list)
                    or not 2 <= len(opts) <= 20
                    or any(
                        not isinstance(v, str) or not v.strip() or len(v) > 200
                        for v in opts
                    )
                ):
                    raise ValueError(
                        "2 bis 20 Antwortmöglichkeiten für die Live-Auswahl angeben."
                    )
                question = dict(
                    title=title,
                    kind=qkind,
                    options=opts if isinstance(opts, list) else [],
                )
                if qkind == "scale":
                    a, b = item.get("min", 1), item.get("max", 5)
                    if type(a) is not int or type(b) is not int or not 0 <= a < b <= 10:
                        raise ValueError("Gültige Skalenbegrenzung angeben.")
                    question.update(min=a, max=b)
                if qkind in ("multi", "rank"):
                    maximum = item.get(
                        "max",
                        item.get(
                            "max_choices" if qkind == "multi" else "top_n",
                            min(3, len(opts)) if qkind == "multi" else len(opts),
                        ),
                    )
                    if type(maximum) is not int or not 1 <= maximum <= len(opts):
                        raise ValueError("Gültige Auswahl- bzw. Ranggrenze angeben.")
                    question.update(
                        max=maximum,
                        **{"max_choices" if qkind == "multi" else "top_n": maximum},
                    )
                if qkind in ("open", "qa", "words"):
                    for flag in (
                        ("filter",) if qkind == "words" else ("approve", "filter")
                    ):
                        value = item.get(flag, True)
                        if type(value) is not bool:
                            raise ValueError(
                                "Moderation und Wortfilter ausdrücklich angeben."
                            )
                        question[flag] = value
                    ranges = (
                        {"max_words": (1, 10, 3), "max_len": (5, 60, 30)}
                        if qkind == "words"
                        else {
                            "max_entries": (1, 20, 3 if qkind == "open" else 5),
                            "max_len": (20, 1000, 280),
                        }
                    )
                    for key, (low, high, default) in ranges.items():
                        value = item.get(key, default)
                        if type(value) is not int or not low <= value <= high:
                            raise ValueError("Beitragsgrenzen prüfen.")
                        question[key] = value
                if qkind == "stars" and (
                    item.get("min", 1) != 1 or item.get("max", 5) != 5
                ):
                    raise ValueError("Sterne verwenden die feste Skala 1 bis 5.")
                if qkind == "slider":
                    a, b, step = (
                        item.get("min", 0),
                        item.get("max", 100),
                        item.get("step", 1),
                    )
                    if (
                        any(type(v) is not int for v in (a, b, step))
                        or not -100000 <= a < b <= 1000000
                        or a > 100000
                        or not 1 <= step <= b - a
                    ):
                        raise ValueError("Schiebereglergrenzen prüfen.")
                    question.update(
                        min=a, max=b, step=step, unit=_text(item, "unit", 12)
                    )
                if qkind == "quiz":
                    correct = item.get("correct")
                    if (
                        not isinstance(correct, list)
                        or not correct
                        or any(
                            type(i) is not int or not 1 <= i <= len(opts)
                            for i in correct
                        )
                        or len(correct) != len(set(correct))
                    ):
                        raise ValueError(
                            "Richtige Antworten als eindeutige Nummern ab 1 angeben."
                        )
                    points, seconds = item.get("points", 1), item.get("seconds", 0)
                    if (
                        type(points) is not int
                        or not 0 <= points <= 1000
                        or type(seconds) is not int
                        or not 0 <= seconds <= 3600
                    ):
                        raise ValueError("Quizpunkte oder Zeitlimit prüfen.")
                    question.update(correct=correct, points=points, seconds=seconds)
                    for flag in ("partial", "nickname"):
                        value = item.get(flag, False)
                        if type(value) is not bool:
                            raise ValueError("Quizoptionen ausdrücklich angeben.")
                        question[flag] = value
                q = LiveQuestion(kind=qkind, title=title)
                err = live.apply_question(q, live_payload(question))
                if err:
                    raise ValueError(err)
                clean.append(question)
        action["questions"] = clean
    return action


def normalize(db, user, raw, findings):
    require(user)
    if raw["tool"] == "create_survey":
        return draft(user, raw)
    kind = "poll" if raw["tool"] == "finalize_poll" else raw.get("record_kind")
    rid = raw.get("id")
    if (
        kind not in MODELS
        or type(rid) is not int
        or not any(r.get("type") == kind and r["id"] == rid for r in findings)
    ):
        raise ValueError("Die Umfrage muss zuvor berechtigt gefunden werden.")
    row = db.get(MODELS[kind], rid)
    if commands.level(db, user, kind, row) < shares.VIEW:
        raise HTTPException(404)
    action = dict(
        tool=raw["tool"], id=rid, record_kind=kind, version=revision(db, kind, row)
    )
    if raw["tool"] == "survey_state":
        op = raw.get("operation")
        if op not in operations(db, user, kind, row):
            raise HTTPException(403, "Diese Umfrageaktion ist nicht verfügbar.")
        action["operation"] = op
    else:
        oid = raw.get("option_id")
        if type(oid) is not int or not any(
            r.get("type") == "poll_option"
            and r["id"] == oid
            and r.get("poll_id") == rid
            for r in findings
        ):
            raise ValueError("Den konkreten Terminvorschlag zuerst finden.")
        if not any(o.id == oid for o in row.options):
            raise HTTPException(404)
        notify = raw.get("notify", False)
        if type(notify) is not bool:
            raise ValueError(
                "Benachrichtigung ausdrücklich als true oder false angeben."
            )
        action.update(option_id=oid, notify=notify)
    target(db, user, action)
    return action


def preview(db, action):
    kind = action["record_kind"]
    if action["tool"] == "create_survey":
        lines = [
            f"{LABELS[kind]} als geschlossenen Entwurf anlegen: {action['title']}",
            action["description"],
        ]
        if kind == "poll":
            lines += [
                f"Ort: {action['location'] or '–'} · Dauer: {action['duration']} Minuten"
            ] + [
                f"{o['date']} {o['start'] or '(ganztägig)'} {o['end']} {o['note']}"
                for o in action["options"]
            ]
        else:
            for q in action["questions"]:
                opts = q.get("options", [])
                text = (
                    ", ".join(o["label"] if isinstance(o, dict) else o for o in opts)
                    if isinstance(opts, list)
                    else str(opts).replace("\n", ", ")
                )
                rules = []
                if kind == "vote":
                    rules.append(f"Auswahl {q['min']} bis {q['max']}")
                    rules.append("Enthaltung " + ("ja" if q["abstain"] else "nein"))
                    if q["kind"] == "points":
                        rules.append(f"Punkte {q['points']}")
                elif q["kind"] == "scale":
                    rules.append(f"Skala {q['min']} bis {q['max']}")
                elif q["kind"] in ("multi", "rank"):
                    rules.append(f"Maximal {q['max']} Antworten oder Plätze")
                elif q["kind"] == "yesno":
                    rules.append("Ja / Nein")
                elif q["kind"] == "stars":
                    rules.append("1 bis 5 Sterne")
                elif q["kind"] == "words":
                    rules.append(f"Maximal {q['max_words']} Begriffe")
                    rules.append("Wortfilter " + ("aktiv" if q["filter"] else "aus"))
                elif q["kind"] in ("open", "qa"):
                    rules.append(
                        "Beiträge mit Freigabe vor Anzeige"
                        if q["approve"]
                        else "Beiträge sofort sichtbar"
                    )
                    rules.append(f"Maximal {q['max_entries']} Beiträge")
                elif q["kind"] == "quiz":
                    rules.append(
                        "Richtige Lösung: "
                        + ", ".join(q["options"][i - 1] for i in q["correct"])
                    )
                    rules.extend(
                        [f"Punkte {q['points']}", f"Zeitlimit {q['seconds']} Sekunden"]
                    )
                elif q["kind"] == "slider":
                    rules.extend(
                        [
                            f"Werte {q['min']} bis {q['max']}",
                            f"Schritt {q['step']} {q['unit']}",
                        ]
                    )
                details = " · ".join(part for part in [text, *rules] if part)
                lines.append(
                    q["title"]
                    + " ("
                    + (votes.KINDS if kind == "vote" else live.KINDS)[q["kind"]][0]
                    + "): "
                    + text
                    + rules
                )
        if kind == "vote":
            lines.append(
                "Geheimhaltung: "
                + votes.SECRECY[action["secrecy"]][0]
                + " · Zugang: "
                + ", ".join(votes.ACCESS[k][0] for k in action["access"])
                + " · Ergebnis: "
                + votes.RESULTS[action["results"]][0]
                + " · Stimme änderbar: "
                + ("ja" if action["allow_change"] else "nein")
            )
        if kind == "live_poll":
            lines.append("Ablauf: " + live.PACING[action["pacing"]][0])
        lines.append(
            "Keine automatische Veröffentlichung, Einladung oder Stimmabgabe. Teilnahme wird separat gestartet."
        )
        return "\n".join(lines)
    row = db.get(MODELS[kind], action["id"])
    if action["tool"] == "finalize_poll":
        option = db.get(PollOption, action["option_id"])
        return f"Termin für „{row.title}“ festlegen: {polls.option_parts(option)['label']}. Umfrage schließen. Teilnehmende per E-Mail informieren: {'ja' if action['notify'] else 'nein'}."
    effects = {
        "publish": "Veröffentlichen und öffentlichen Teilnahmelink aktivieren",
        "reopen": "Erneut öffnen (bestehende Antworten bleiben)",
        "close": "Beenden; bei Abstimmungen Ergebnis festschreiben",
        "start": "Starten; ausstehende persönliche Einladungen werden gegebenenfalls versendet",
        "pause": "Anhalten; bestehende Stimmen bleiben",
        "open": "Live-Umfrage öffnen; vorhandene Antworten bleiben",
    }
    return LABELS[kind] + f" „{row.title}“: " + effects[action["operation"]]


def execute(db, user, action):
    from .leave import lock

    lock(db)
    kind = action["record_kind"]
    if action["tool"] == "create_survey":
        action = draft(user, action)
        label = preview(db, action)
        if kind == "poll":
            row = Poll(
                owner_id=user.id,
                title=action["title"],
                description=action["description"],
                location=action["location"],
                duration_minutes=action["duration"],
                closed=True,
                published_at=None,
                public_token=None,
            )
            db.add(row)
            polls.set_options(
                db, row, polls.parse_options(json.dumps(action["options"]))
            )
        elif kind == "vote":
            row = Vote(
                owner_id=user.id,
                title=action["title"],
                description=action["description"],
                status="draft",
                secrecy=action["secrecy"],
                access=",".join(action["access"]),
                results=action["results"],
                allow_change=action["allow_change"],
                public_token=new_link_token(),
            )
            err = votes.set_questions(db, row, action["questions"])
            if err:
                raise HTTPException(422, err)
            db.add(row)
        else:
            row = LivePoll(
                owner_id=user.id,
                title=action["title"],
                description=action["description"],
                status="draft",
                pacing=action["pacing"],
                public_token=new_link_token(),
            )
            db.add(row)
            for i, item in enumerate(action["questions"]):
                q = LiveQuestion(kind=item["kind"], title=item["title"], position=i)
                err = live.apply_question(q, live_payload(item))
                if err:
                    raise HTTPException(422, err)
                row.questions.append(q)
        db.flush()
    else:
        row = target(db, user, action)
        label = preview(db, action)
        if action["tool"] == "survey_state":
            commands.state(db, user, kind, row, action["operation"])
        else:
            commands.choose_final(db, user, row, action["option_id"], action["notify"])
    url = {
        "poll": f"/polls/{row.id}",
        "vote": f"/votes/{row.id}",
        "live_poll": f"/votes/live/{row.id}",
    }[kind]
    return dict(label=label, target_id=row.id, url=url)
