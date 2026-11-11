"""Survey lifecycle commands shared by native routes and confirmed agent tools."""

from fastapi import HTTPException
from . import shares, poll_lifecycle as lifecycle, polls, votes, live
from .db import utcnow
from .security import new_link_token


def level(db, user, kind, row):
    if not row or not user.active:
        return 0
    if kind == "live_poll":
        return shares.OWNER if user.can("votes") and lifecycle.owner(row, user) else 0
    return shares.access_level(db, kind, row, user)


def validate_state(db, user, kind, row, operation):
    access = level(db, user, kind, row)
    need = (
        shares.EDIT
        if kind == "poll" and operation in ("close", "reopen")
        else shares.INVITE
    )
    if access < need:
        raise HTTPException(403, "Für diese Umfrage fehlt die erforderliche Freigabe.")
    lifecycle.mutable(row)
    if kind == "poll":
        if operation not in ("publish", "reopen", "close"):
            raise HTTPException(422, "Unbekannte Terminumfrage-Aktion.")
        if operation in ("publish", "reopen"):
            lifecycle.require_owner(row, user)
            if row.expires_at and row.expires_at < utcnow():
                raise HTTPException(409, "Bitte zuerst die abgelaufene Frist ändern.")
            if not row.options:
                raise HTTPException(409, "Terminvorschläge fehlen.")
    elif kind == "vote":
        if operation not in ("start", "pause", "close"):
            raise HTTPException(422, "Unbekannte Abstimmungsaktion.")
        if operation == "start":
            lifecycle.require_owner(row, user)
            if row.status == "closed":
                raise HTTPException(
                    409,
                    "Ein festgeschriebenes Ergebnis kann nicht wieder geöffnet werden.",
                )
            if not row.questions or (row.ends_at and row.ends_at < utcnow()):
                raise HTTPException(
                    409, "Fragen fehlen oder die Abstimmung ist abgelaufen."
                )
        if operation == "close" and access < shares.EDIT and row.results != "live":
            raise HTTPException(403)
        if operation == "pause" and row.status != "open":
            raise HTTPException(
                409, "Nur eine laufende Abstimmung kann angehalten werden."
            )
        if operation == "close" and row.status == "closed":
            raise HTTPException(409, "Das Ergebnis ist bereits festgeschrieben.")
    else:
        if operation not in ("open", "close"):
            raise HTTPException(422, "Unbekannte Live-Umfrage-Aktion.")
        if operation == "open" and not row.questions:
            raise HTTPException(409, "Bitte zuerst mindestens eine Frage anlegen.")


def state(db, user, kind, row, operation):
    validate_state(db, user, kind, row, operation)
    count = 0
    if kind == "poll":
        if operation in ("publish", "reopen"):
            row.published_at = row.published_at or utcnow()
            row.public_token = row.public_token or new_link_token()
            row.closed = False
        else:
            row.closed = True
    elif kind == "vote":
        if operation == "start":
            row.status = "open"
            row.opened_at = row.opened_at or utcnow()
            count = votes.send_pending_invites(db, row, user)
        elif operation == "pause":
            row.status = "draft"
        else:
            votes.close(db, row)
    elif operation == "open":
        row.status = "open"
        row.opened_at = row.opened_at or utcnow()
        if row.current_id is None:
            row.current_id = row.questions[0].id
        for q in row.questions:
            if row.pacing == "free" or q.id == row.current_id:
                live.start_timer(q)
    else:
        row.status = "closed"
    return count


def choose_final(db, user, row, option_id, notify=False):
    if level(db, user, "poll", row) < shares.EDIT:
        raise HTTPException(403)
    lifecycle.mutable(row)
    option = next((o for o in row.options if o.id == option_id), None)
    if option is None:
        raise HTTPException(404, "Dieser Terminvorschlag gehört nicht zur Umfrage.")
    row.final_option_id = option.id
    row.closed = True
    lifecycle.mark_used(row)
    return option, polls.announce_final(db, row, user) if notify else 0
