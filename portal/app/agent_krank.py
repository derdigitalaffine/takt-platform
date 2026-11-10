"""Local health-data routing. No provider, RAG or conversation storage is used."""
import hashlib
import json
import re
import secrets
from datetime import date, timedelta
from fastapi import HTTPException
from sqlalchemy import select
from . import krank
from .db import KrankReport, get_settings

TOOLS = {'set_krank_status', 'add_krank_note', 'send_krank_message'}
FIELDS = {'first_name', 'last_name', 'email', 'employer', 'insured', 'personnel_no', 'from', 'to', 'doctor', 'first', 'child_name', 'child_dob', 'remarks'}
SIGNAL = re.compile(r'\b(?:krank\w*|kindkrank\w*|eau|(?:mit|ohne)\s+(?:eine[r]?\s+)?au\b|arbeitsunfähig\w*|au-bescheinigung|\bKM-\d{4}-\d+)', re.I)
DAY = r'(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4}|heute|morgen|gestern)'


def require(user):
    from .agent import require as module_access
    module_access(user, 'krank')


def version(row):
    values = [row.status, str(row.status_at), str(row.updated_at), row.employer_id, row.data_enc,
              [e.id for e in row.events], [f.id for f in row.files]]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def target(db, user, action):
    require(user)
    row = db.get(KrankReport, action['id'])
    if not krank.uses_module(db, user) or not row or not krank.can_see(db, user, row):
        raise HTTPException(404, 'Krankmeldung nicht zur Bearbeitung freigegeben.')
    if 'version' in action and version(row) != action['version']:
        raise HTTPException(409, 'Die Krankmeldung wurde geändert. Bitte neu vorbereiten.')
    if action['tool'] == 'set_krank_status' and (action['status'] not in krank.allowed_statuses(row) or action['status'] == row.status):
        raise HTTPException(422, 'Dieser Statuswechsel ist nicht verfügbar.')
    return row


def normalize(db, user, raw, findings):
    if type(raw.get('id')) is not int or not any(r.get('type') == 'krank' and r['id'] == raw['id'] for r in findings):
        raise ValueError('Die Krankmeldung muss lokal und berechtigt gefunden werden.')
    action = dict(tool=raw['tool'], id=raw['id'])
    if action['tool'] == 'set_krank_status':
        if raw.get('status') not in krank.STATUSES:
            raise ValueError('Unbekannter Krankmeldestatus.')
        action['status'] = raw['status']
        key, limit = 'note', 2000
    else:
        key, limit = 'text', 4000 if action['tool'] == 'add_krank_note' else 2000
    text = raw.get(key, '')
    if not isinstance(text, str) or len(text) > limit or (key == 'text' and not text.strip()):
        raise ValueError('Bitte eine gültige Nachricht oder Notiz angeben.')
    action[key] = text.strip()
    row = target(db, user, action)
    action['version'] = version(row)
    return action


def preview(db, action):
    row = db.get(KrankReport, action['id'])
    if action['tool'] == 'set_krank_status':
        return f"{row.ref_no}: {krank.status_label(row.status)} → {krank.status_label(action['status'])}. Hinweis für die meldende Person: {action['note'] or '–'}"
    if action['tool'] == 'add_krank_note':
        return f"{row.ref_no}: interne Notiz speichern (nicht auf der Statusseite):\n{action['text']}"
    return f"{row.ref_no}: Nachricht auf der Statusseite veröffentlichen und gegebenenfalls E-Mail versenden:\n{action['text']}"


def execute(db, user, action):
    row = target(db, user, action)
    label = preview(db, action)
    if action['tool'] == 'set_krank_status':
        krank.set_status(db, row, action['status'], user, action['note'])
    elif action['tool'] == 'add_krank_note':
        krank.add_note(db, row, user, action['text'])
    else:
        krank.message(db, row, user, action['text'])
    return dict(label=label, target_id=row.id, url=f'/krankmelder/{row.id}')


def _day(value):
    if value.casefold() in ('heute', 'morgen', 'gestern'):
        return (krank.today() + timedelta(days={'heute': 0, 'morgen': 1, 'gestern': -1}[value.casefold()])).isoformat()
    try:
        if '.' in value:
            d, m, y = value.split('.')
            return date(int(y), int(m), int(d)).isoformat()
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ''


def creation_fields(prompt):
    fields = {}
    for key, prefix in [('from', r'(?:vom|von|seit|ab)'), ('to', r'bis(?:\s+einschließlich)?'),
                        ('doctor', r'festgestellt(?:\s+am)?'), ('child_dob', r'(?:geboren|geburtsdatum)(?:\s+am)?')]:
        matches = re.findall(prefix + r'\s+(' + DAY + r')\b', prompt, re.I)
        if len(matches) == 1 and (value := _day(matches[0])):
            fields[key] = value
    if re.search(r'folgebescheinigung', prompt, re.I):
        fields['first'] = '0'
    if re.search(r'privat\s+versichert', prompt, re.I):
        fields['insured'] = 'private'
    return fields


def load_creation(request, user, nonce, kind):
    from .main import stash_get
    if user is None:
        raise HTTPException(401, "Bitte erneut anmelden.")
    require(user)
    saved = stash_get(request, 'takt-agent-krank')
    if (not saved or not nonce or not nonce.isascii() or not secrets.compare_digest(nonce, saved['nonce'])
            or saved['user_id'] != user.id or saved['kind'] != kind):
        raise HTTPException(409, 'Dieser Krankmelde-Vorschlag ist abgelaufen. Bitte neu vorbereiten.')
    return saved


def prepare(request, db, user, prompt):
    """Only exact local references and unambiguous dates; never diagnose or infer a certificate."""
    from .main import stash_put
    from . import agent, agent_drafts
    require(user)
    ref = re.findall(r'\bKM-\d{4}-\d+\b', prompt, re.I)
    if ref:
        if len(set(s.upper() for s in ref)) != 1:
            return response('Bitte genau eine Krankmeldung zur Bearbeitung auswählen.', '/krankmelder' if krank.uses_module(db, user) else '/krank/meine')
        row = db.scalar(select(KrankReport).where(KrankReport.ref_no == ref[0].upper()))
        # Never reveal the existence of another employer's reports.
        if not krank.uses_module(db, user) or not row or not krank.can_see(db, user, row):
            raise HTTPException(404, 'Krankmeldung nicht zur Bearbeitung freigegeben.')
        raw = None
        note = re.search(r'\b(Notiz|Nachricht)\s*:\s*(.+)$', prompt, re.I | re.S)
        if note:
            raw = dict(tool='add_krank_note' if note[1].casefold() == 'notiz' else 'send_krank_message', id=row.id, text=note[2])
        elif re.search(r'\b(?:setz\w*|markier\w*|bearbeit\w*|abschließ\w*)\b', prompt, re.I):
            states = [key for key, (label, *_) in krank.STATUSES.items() if re.search(r'(?<!\w)' + re.escape(label) + r'(?!\w)', prompt, re.I)]
            if len(states) == 1:
                raw = dict(tool='set_krank_status', id=row.id, status=states[0])
        krank.audit(db, user, row, 'agent_lookup')
        db.commit()
        if raw:
            action = normalize(db, user, raw, [dict(type='krank', id=row.id)])
            nonce = secrets.token_urlsafe(24)
            plan = dict(nonce=nonce, user_id=user.id, actions=[action])
            stash_put(request, 'takt-agent-plan', plan)
            return response('Der Krankmelde-Vorschlag wird lokal in der Fachmaske vorbereitet. Bitte dort prüfen und bestätigen.', agent_drafts.url(plan), [preview(db, action)], nonce)
        return response('Öffne die Krankmeldung für die weitere Bearbeitung. Es wurde nichts geändert.', f'/krankmelder/{row.id}')
    if re.search(r'(?:meine|eigene)\s+krankmeldung', prompt, re.I):
        return response('Hier findest du deine eigenen verknüpften Krankmeldungen.', '/krank/meine')
    if re.search(r'\b(?:such\w*|zeig\w*|liste|übersicht|offene)\b', prompt, re.I):
        return response('Nutze die berechtigte Krankmeldeliste zum Suchen und Auswählen.', '/krankmelder/liste' if krank.uses_module(db, user) else '/krank/meine')
    kinds = set()
    for key, pattern in {
        'child': r'kind\s*krank|kinderkrank', 'eau': r'\beau\b|elektronische\s+au',
        'simple': r'ohne\s+(?:eine\s+)?au|ohne\s+bescheinigung',
        'au': r'mit\s+(?:einer\s+)?au|au-bescheinigung|privat\s+versichert',
    }.items():
        if re.search(pattern, prompt, re.I):
            kinds.add(key)
    kind = next(iter(kinds)) if len(kinds) == 1 else None
    if not kind:
        return response('Wähle im Krankmelder den zutreffenden Meldeweg: ohne AU (nur heute), mit AU, eAU oder Kind krank. Angaben bleiben außerhalb des Sprachmodells.', '/krank')
    if kind not in krank.enabled_kinds(get_settings(db)):
        raise HTTPException(422, 'Dieser Meldeweg ist derzeit nicht freigeschaltet. Bitte im Krankmelder einen verfügbaren Weg wählen.')
    if kind == 'simple' and (krank.today().weekday() > 4 or re.search(r'\b(?:morgen|gestern|bis|seit|vom|von|ab)\b|\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.', prompt, re.I)):
        return response('Ohne AU ist nur die Meldung für heute an einem Werktag möglich. Bitte den zutreffenden Zeitraum und Meldeweg im Krankmelder wählen.', '/krank')
    fields = creation_fields(prompt)
    emps = [e for e in krank.employers(db) if e.active]
    matches = [e for e in emps if e.name.casefold() in prompt.casefold()]
    if len(matches) == 1 or len(emps) == 1:
        fields['employer'] = str((matches or emps)[0].id)
    nonce = secrets.token_urlsafe(24)
    stash_put(request, 'takt-agent-krank', dict(nonce=nonce, user_id=user.id, kind=kind, fields=fields))
    return response('Der passende Krankmeldeweg ist vorbereitet. Nur eindeutige Angaben sind übernommen. Prüfe fehlende Pflichtangaben und die Vorschau vor dem Absenden. Deine Angaben werden nicht an das Sprachmodell oder den Chatverlauf übergeben.', f'/krank/{kind}?agent_health={nonce}', ['Krankmeldung in der geschützten Fachmaske prüfen.'])


def response(message, url, proposals=None, nonce=''):
    return dict(mode='private', message=message, open_url=url, proposals=proposals or [], plan_id=nonce, steps=[], results=[], sources=[])


def safe_history(messages):
    """Old conversations may predate the private handoff; never replay those health turns."""
    result = []
    private_turn = False
    for message in messages:
        content = message.get('content', '')
        health = isinstance(content, str) and bool(SIGNAL.search(content))
        if message.get('role') == 'user':
            private_turn = health
        if not health and not private_turn:
            result.append(message)
    return result
