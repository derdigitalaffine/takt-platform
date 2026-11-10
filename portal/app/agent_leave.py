"""Bounded leave workflows; domain commands own authorization and business rules."""
from fastapi import HTTPException
from sqlalchemy import select, or_
from . import leave, organization as org
from .db import User
from .leave_models import LeaveRequest
from .leave_admin import removed_ids

TOOLS = {'create_leave', 'edit_leave', 'leave_command'}
COMMANDS = {
    'request': 'Antrag einreichen', 'bind': 'Verbindlich einplanen',
    'approve': 'Genehmigen / nächste Genehmigungsstufe', 'reject': 'Ablehnen',
    'cancel': 'Stornieren', 'request_cancel': 'Stornierung anfragen',
    'reject_cancel': 'Stornoanfrage ablehnen', 'request_exception': 'Ausnahmeentscheidung anfragen',
    'attest': 'Externe Genehmigung selbst bestätigen (Selbstauskunft)',
}


def accessible(db, user, row):
    from .routes_leave import can_decide_request, can_see_leave_details
    return bool(row and (can_decide_request(db, user, row) or
                (can_see_leave_details(db, user, row.person_id) and leave.can_plan(db, user, row.person_id))) and
                db.scalar(select(LeaveRequest.id).where(LeaveRequest.id == row.id, LeaveRequest.id.not_in(removed_ids()))) is not None)


def candidates(db, user, row):
    """Conservative operation hints, not authorization. Exact command is validated below."""
    from .routes_leave import can_decide_request
    cfg = leave.policy(db, row.org_id)
    operations = []
    planner = leave.can_plan(db, user, row.person_id)
    if planner and row.status == 'planned':
        if cfg.workflow == 'internal':
            operations.append('request')
        elif cfg.workflow == 'planning':
            operations.append('bind')
        elif cfg.external_attestation and row.person_id == user.id:
            operations.append('attest')
        if cfg.workflow != 'internal' and not cfg.notify_only_warnings:
            operations.append('request_exception')
    if can_decide_request(db, user, row):
        if row.status == 'requested':
            operations.extend(['approve', 'reject'])
        if row.cancel_requested:
            operations.append('reject_cancel')
    if row.effective_json and cfg.workflow == 'internal':
        if user.id != row.person_id and org.allows(db, user, leave.cancellation_unit(db, row), 'approve'):
            operations.append('cancel')
        elif planner and not row.cancel_requested:
            operations.append('request_cancel')
    elif planner and row.status != 'cancelled':
        operations.append('cancel')
    return operations


def search(db, user, spec):
    from .agent import require, _like
    require(user, 'leave')
    scope = 'own' if spec['tool'] == 'search_my_leave' else str(spec.get('scope') or 'own')
    if scope == 'all':
        scope = 'own'
    if scope not in ('own', 'manageable', 'decisions'):
        raise ValueError('Urlaubssuche: own, manageable oder decisions wählen.')
    query = select(LeaveRequest).join(User, User.id == LeaveRequest.person_id).where(LeaveRequest.id.not_in(removed_ids()))
    if scope == 'own':
        query = query.where(LeaveRequest.person_id == user.id)
    elif scope == 'decisions':
        query = query.where(or_(LeaveRequest.status == 'requested', LeaveRequest.cancel_requested.is_(True)))
    state = spec.get('status')
    if state:
        if state not in ('planned', 'requested', 'binding', 'rejected', 'cancelled'):
            raise ValueError('Unbekannter Urlaubsstatus.')
        query = query.where(LeaveRequest.status == state)
    phrase = str(spec.get('query') or '').strip()[:100]
    if phrase:
        if phrase.lstrip('#').isdigit():
            query = query.where(LeaveRequest.id == int(phrase.lstrip('#')))
        else:
            query = query.where(or_(User.name.ilike(_like(phrase), escape='\\'), LeaveRequest.starts_on.contains(phrase), LeaveRequest.ends_on.contains(phrase)))
    out = []
    from .routes_leave import can_decide_request
    for row in db.scalars(query.order_by(LeaveRequest.starts_on.desc(), LeaveRequest.id.desc())):
        if not accessible(db, user, row) or (scope == 'decisions' and not can_decide_request(db, user, row)):
            continue
        person = db.get(User, row.person_id)
        out.append(dict(type='leave', id=row.id, title=f'{person.name}: {row.starts_on} bis {row.ends_on}',
                        starts_on=row.starts_on, ends_on=row.ends_on, start_half=row.start_half, end_half=row.end_half,
                        status=row.status, cancel_requested=bool(row.cancel_requested),
                        editable=leave.can_plan(db, user, row.person_id), operations=candidates(db, user, row),
                        workflow=leave.policy(db, row.org_id).workflow, url=f'/urlaub/vorgang/{row.id}'))
        if len(out) == 20:
            break
    return out


def policy_snapshot(db, unit):
    cfg = leave.policy(db, unit)
    return [getattr(cfg, k) for k in ('org_id', 'version', 'workflow', 'sync_absence', 'minimum', 'conflict_mode',
            'external_attestation', 'advanced', 'minimum_capacity', 'internal_account', 'approval_units', 'notify_only_warnings', 'holiday_state')]


def target(db, user, action):
    from .agent import require
    require(user, 'leave')
    row = db.get(LeaveRequest, action['id']) if action['tool'] != 'create_leave' else None
    if action['tool'] != 'create_leave' and not accessible(db, user, row):
        raise HTTPException(403, 'Dieser Urlaub ist für dich nicht zur Bearbeitung freigegeben.')
    uid = row.person_id if row else user.id
    unit = leave.primary(db, uid)
    if unit != action['org_id'] or policy_snapshot(db, unit) != action['policy_snapshot']:
        raise HTTPException(409, 'Zuordnung oder Urlaubsverfahren geändert. Bitte neu planen.')
    if row and row.version != action['version']:
        raise HTTPException(409, 'Der Urlaub wurde inzwischen geändert. Bitte neu planen.')
    if action['tool'] in ('create_leave', 'edit_leave'):
        if not leave.can_plan(db, user, uid):
            raise HTTPException(403)
        leave.period(uid, action)
    return row


def validate(db, user, action):
    target(db, user, action)
    if action['tool'] == 'leave_command':
        # The real service checks four-eyes, escalation, staffing, accounts,
        # overlaps, cancellation, external attestation and notifications.
        # Roll back ALL effects, including audit/outbox/mirrors and lock counter.
        savepoint = db.begin_nested()
        try:
            leave.command(db, user, action['id'], action['command'], action['version'], action['reason'])
            db.flush()
        finally:
            savepoint.rollback()


def normalize(db, user, raw, findings):
    from .agent import require
    require(user, 'leave')
    tool = raw['tool']
    action = dict(tool=tool, requester_id=user.id)
    row = None
    if tool != 'create_leave':
        rid = raw.get('id')
        if type(rid) is not int or not any(r.get('type') == 'leave' and r['id'] == rid for r in findings):
            raise ValueError('Der Urlaubsantrag muss zuvor berechtigt gefunden werden.')
        row = db.get(LeaveRequest, rid)
        if not accessible(db, user, row):
            raise HTTPException(403)
        action.update(id=rid, version=row.version)
    uid = row.person_id if row else user.id
    unit = leave.primary(db, uid)
    from .routes_leave import readable
    display_unit = next((oid for oid in org.active_path(db, unit) if readable(db, user, oid)), None)
    if display_unit is None:
        raise HTTPException(403)
    action.update(person_id=uid, org_id=unit, display_unit=display_unit, policy_snapshot=policy_snapshot(db, unit))
    if tool in ('create_leave', 'edit_leave'):
        for key, default in (('starts_on', ''), ('ends_on', ''), ('start_half', 'am'), ('end_half', 'pm')):
            value = raw.get(key, default)
            if not isinstance(value, str) or len(value) > 10:
                raise ValueError('Gültigen Urlaubszeitraum angeben.')
            action[key] = value
        leave.period(uid, action)
    else:
        command = raw.get('command')
        if command not in COMMANDS:
            raise ValueError('Unbekannte Urlaubsaktion.')
        if command not in candidates(db, user, row):
            raise HTTPException(403, 'Diese Urlaubsaktion ist für dich nicht verfügbar.')
        reason = raw.get('reason', '')
        if not isinstance(reason, str) or len(reason) > 2000:
            raise ValueError('Begründung mit höchstens 2000 Zeichen angeben.')
        action.update(command=command, reason=reason.strip())
    validate(db, user, action)
    return action


def preview(db, action):
    person = db.get(User, action['person_id'])
    if action['tool'] in ('create_leave', 'edit_leave'):
        return (f"Urlaubsentwurf {'ändern' if action['tool'] == 'edit_leave' else 'anlegen'} für {person.name}: "
                f"{action['starts_on']} ({action['start_half']}) bis einschließlich {action['ends_on']} ({action['end_half']}). "
                'Keine automatische Einreichung oder Genehmigung. Ein bisher verbindlicher Zeitraum gilt bis zur erneuten Entscheidung weiter.')
    row = db.get(LeaveRequest, action['id'])
    return (f"{COMMANDS[action['command']]}: {person.name}, {row.starts_on} ({row.start_half}) bis {row.ends_on} ({row.end_half}). "
            f"Status bisher: {row.status}. Begründung: {action['reason'] or '–'}. Die bestehenden Benachrichtigungsregeln gelten.")


def execute(db, user, action):
    target(db, user, action)
    label = preview(db, action)
    if action['tool'] == 'leave_command':
        row = leave.command(db, user, action['id'], action['command'], action['version'], action['reason'])
    else:
        row = leave.save(db, user, action, action.get('id'))
    return dict(label=label, target_id=row.id, url=f'/urlaub/vorgang/{row.id}')
