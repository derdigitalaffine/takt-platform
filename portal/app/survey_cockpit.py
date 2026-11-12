"""Permission-filtered, read-only participation cockpit.

Adapters never touch a ballot body, an individual live device hash, or a
survey answer. Each engine keeps its existing access and publication rules.
"""
from sqlalchemy import and_, case, func, select

from . import forms as fm, polls as pl, shares, votes as vt
from .db import (Form, FormInvite, FormResponse, Poll, PollParticipant,
                 Vote, VoteVoter, LivePoll, LiveAnswer)


KINDS = {
    'form': ('Formularumfrage', 'fa-clipboard-list'),
    'poll': ('Terminumfrage', 'fa-calendar-check'),
    'vote': ('Abstimmung', 'fa-check-to-slot'),
    'live': ('Live-Umfrage', 'fa-tower-broadcast'),
}


def _allowed(db, user, model, *, shared=(), minimum=2):
    """Owners/admins and explicitly invited managers; viewers do not see
    participant statistics through this aggregate management interface.
    """
    own = select(model) if user.is_admin else select(model).where(model.owner_id == user.id)
    rows = {obj.id: obj for obj in db.scalars(own)}
    for obj, level in shared:
        if level >= minimum:
            rows.setdefault(obj.id, obj)
    return rows


def _group_counts(db, model, foreign_id, ids, *expressions):
    if not ids:
        return {}
    return {row[0]: tuple(int(value or 0) for value in row[1:])
            for row in db.execute(select(foreign_id, *expressions).where(
                foreign_id.in_(ids)).group_by(foreign_id)).all()}


def collect(db, user, modules: set[str]) -> list[dict]:
    out = []

    def append(kind, obj, *, invited=None, answered=0, registered=0,
               pending=None, note='', destination=''):
        status = 'Archiviert' if obj.archived_at else (
            ('Läuft' if kind in {'vote', 'live'} else 'Offen')
            if {'form': lambda: fm.is_open(obj),
                'poll': lambda: pl.is_open(obj),
                'vote': lambda: vt.is_open(obj),
                'live': lambda: obj.status == 'open'}[kind]()
            else ('Entwurf' if kind == 'live' and obj.status == 'draft'
                  else 'Entwurf' if kind == 'vote' and obj.status == 'draft'
                  else 'Beendet'))
        rate = round(registered * 100 / invited, 1) if invited else None
        out.append(dict(kind=kind, id=obj.id, title=obj.title, description=obj.description,
                        status=status, updated=obj.updated_at, invited=invited,
                        registered=registered, pending=pending, answers=answered,
                        rate=rate, note=note, url=destination))

    if 'forms' in modules:
        models = _allowed(db, user, Form, shared=fm.shared_with(db, user), minimum=fm.INVITE)
        forms = [f for f in models.values() if f.kind == 'survey' and f.deleted_at is None]
        ids = [f.id for f in forms]
        invited = _group_counts(db, FormInvite, FormInvite.form_id, ids,
                                func.count(FormInvite.id), func.count(FormInvite.submitted_at))
        answers = _group_counts(db, FormResponse, FormResponse.form_id, ids, func.count(FormResponse.id))
        for form in forms:
            total, done = invited.get(form.id, (0, 0))
            append('form', form, invited=total, registered=done,
                   pending=total-done, answered=answers.get(form.id, (0,))[0],
                   note=('Anonyme Antworten sind nicht einzelnen Einladungen zugeordnet'
                         if form.anonymous else 'Antwortzahlen umfassen auch öffentliche Teilnahmen'),
                   destination=f'/forms/{form.id}/share')

    if 'polls' in modules:
        polls = _allowed(db, user, Poll, shared=shares.shared_with(db, 'poll', user),
                         minimum=shares.INVITE)
        pids = list(polls)
        invited = _group_counts(
            db, PollParticipant, PollParticipant.poll_id, pids,
            func.count(PollParticipant.invited_at),
            func.sum(case((and_(PollParticipant.invited_at.is_not(None),
                                PollParticipant.answered_at.is_not(None)), 1), else_=0)),
            func.count(PollParticipant.answered_at))
        for poll in polls.values():
            total, done, answers = invited.get(poll.id, (0, 0, 0))
            append('poll', poll, invited=total, registered=done, pending=total-done,
                   answered=answers, note='Öffentliche Antworten sind in der Gesamtzahl enthalten',
                   destination=f'/polls/{poll.id}?tab=share')

        votes = _allowed(db, user, Vote, shared=shares.shared_with(db, 'vote', user),
                         minimum=shares.INVITE)
        vids = list(votes)
        voter_counts = _group_counts(
            db, VoteVoter, VoteVoter.vote_id, vids,
            func.sum(case((VoteVoter.confirmed.is_(True), 1), else_=0)),
            func.sum(case((and_(VoteVoter.confirmed.is_(True),
                                VoteVoter.voted.is_(True)), 1), else_=0)))
        for vote in votes.values():
            eligible, voted = voter_counts.get(vote.id, (0, 0))
            append('vote', vote, invited=eligible, registered=voted, pending=eligible-voted,
                   answered=voted, note='Nur Beteiligung: keine Verknüpfung zu Stimmzetteln',
                   destination=f'/votes/{vote.id}?tab=share')

        live = _allowed(db, user, LivePoll)
        live_ids = list(live)
        devices = _group_counts(db, LiveAnswer, LiveAnswer.poll_id, live_ids,
                                func.count(func.distinct(LiveAnswer.device)))
        for poll in live.values():
            append('live', poll, invited=None, registered=0, pending=None,
                   answered=devices.get(poll.id, (0,))[0],
                   note='Anonyme Gerätebeteiligung · keine personenbezogene Rücklaufquote',
                   destination=f'/votes/live/{poll.id}?tab=moderate')
    return sorted(out, key=lambda row: (row['updated'], row['kind'], row['id']), reverse=True)


def totals(rows: list[dict]) -> dict:
    return {'surveys': len(rows),
            'invitations': sum(row['invited'] or 0 for row in rows),
            'completed': sum(row['registered'] for row in rows),
            'pending': sum(row['pending'] or 0 for row in rows),
            'live': sum(row['kind'] == 'live' and row['status'] == 'Läuft' for row in rows)}
