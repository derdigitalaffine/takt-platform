"""Read-only, privacy-conscious personal participation index.

The existing form, appointment poll and formal vote engines own all access and
submission rules. Live participation is intentionally not attributed to a user:
the device hash is an anonymous participation key, not a portal identity.
"""
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

from . import forms as fm, polls as pl, votes as vt
from .db import Form, FormInvite, FormResponse, Poll, PollParticipant, Vote, VoteVoter


def collect(db, user, modules: set[str]) -> list[dict]:
    """Personal statuses without fetching, serializing or correlating answer contents."""
    rows = {}

    def add(kind, ident, title, description, *, complete, available, date, due,
            url='', action='', label='', note=''):
        key = (kind, ident)
        old = rows.get(key)
        # Multiple invitations or recorded responses represent ONE survey here.
        if old and old['complete'] and not complete:
            return
        if old and complete and old['complete'] and old['date'] and date and old['date'] >= date:
            return
        status = 'done' if complete else 'open' if available else 'closed'
        rows[key] = dict(kind=kind, id=ident, title=title, description=description,
                         status=status, complete=bool(complete), date=date, due=due,
                         url=url if action else '', action=action, label=label, note=note)

    if 'forms' in modules:
        invitations = list(db.scalars(select(FormInvite).join(Form).options(
            joinedload(FormInvite.form)).where(
            or_(FormInvite.user_id == user.id, FormInvite.email == user.email),
            Form.kind == 'survey', Form.deleted_at.is_(None))))
        # Only identifiable responses; anonymous forms never supply a user-facing
        # response record because that would silently re-identify the content.
        responses = list(db.scalars(select(FormResponse).join(Form).options(
            joinedload(FormResponse.form)).where(
            Form.kind == 'survey', Form.anonymous.is_(False),
            Form.deleted_at.is_(None),
            or_(FormResponse.user_id == user.id,
                and_(FormResponse.source == 'invite', FormResponse.email == user.email))
        ).order_by(FormResponse.created_at.desc())))
        last_response = {}
        for resp in responses:
            last_response.setdefault(resp.form_id, resp)
        for inv in invitations:
            form = inv.form
            own = last_response.get(inv.form_id) if not form.anonymous else None
            done_at = (own.created_at if own else None) or inv.submitted_at
            available = fm.is_open(form)
            url = f'/f/i/{inv.token}' if available else ''
            add('form', form.id, form.title, form.description,
                complete=bool(done_at), available=available, date=done_at or inv.invited_at,
                due=form.expires_at, url=url,
                action=('Erneut ausfüllen' if done_at else 'Ausfüllen') if available and (not done_at or form.multiple) else '',
                note='Anonyme Teilnahme – Antworten werden nicht im Benutzerprofil gespeichert' if form.anonymous else '')
        for resp in last_response.values():
            form = resp.form
            if ('form', form.id) in rows:
                continue
            available = fm.is_open(form)
            can_repeat = available and bool(form.multiple and form.public_token)
            add('form', form.id, form.title, form.description,
                complete=True, available=available, date=resp.created_at, due=form.expires_at,
                url=f'/f/{form.public_token}' if can_repeat else '',
                action='Erneut ausfüllen' if can_repeat else '')

    if 'polls' in modules:
        # Never infer identity from an unverified email entered in a PUBLIC poll.
        # An organizer's invitation with the same account email is authoritative.
        people = list(db.scalars(select(PollParticipant).join(Poll).options(
            joinedload(PollParticipant.poll)).where(
            or_(PollParticipant.user_id == user.id,
                and_(PollParticipant.invited_at.is_not(None), PollParticipant.email == user.email)),
            Poll.published_at.is_not(None))))
        for p in people:
            poll = p.poll
            available = pl.is_open(poll)
            complete = p.answered_at is not None
            add('poll', poll.id, poll.title, poll.description,
                complete=complete, available=available, date=p.answered_at or p.invited_at,
                due=poll.expires_at, url=f'/t/p/{p.edit_token}',
                action=('Antwort ändern' if complete else 'Antworten') if available else
                       ('Teilnahme ansehen' if complete else ''),
                note='Termin festgelegt' if poll.final_option_id else '')

        # The voter registry stores whether the person voted, not how they voted.
        # Never join this personal list to VoteBallot: secret ballots stay secret.
        voters = list(db.scalars(select(VoteVoter).join(Vote).options(
            joinedload(VoteVoter.vote)).where(
            or_(VoteVoter.user_id == user.id,
                and_(VoteVoter.source == 'invite', VoteVoter.email == user.email)))))
        for v in voters:
            vote = v.vote
            if vote.status == 'draft' or not v.confirmed:
                continue
            available = vt.can_vote(vote, v)
            add('vote', vote.id, vote.title, vote.description,
                complete=v.voted, available=available, date=v.invited_at or v.created_at,
                due=vote.ends_at, url=f'/v/p/{v.token}',
                action=('Stimme ändern' if v.voted else 'Abstimmen') if available else
                       ('Teilnahmestatus ansehen' if v.voted else ''),
                note='Geheime Abstimmung – keine Einsicht in den Stimmzettel' if vote.secrecy != 'open' else '')

    # Open first, then completed, then closed; deadline/last interaction for ordering.
    priority = {'open': 0, 'done': 1, 'closed': 2}
    return sorted(rows.values(), key=lambda row: (
        priority[row['status']],
        row['due'] if row['status'] == 'open' and row['due'] else datetime.max,
        -(row['date'] or datetime.min).timestamp() if row['date'] and row['date'].year > 1970 else 0,
        row['kind'], row['id'],
    ))


def summary(rows: list[dict]) -> dict:
    return {key: sum(row['status'] == key for row in rows) for key in ('open', 'done', 'closed')}
