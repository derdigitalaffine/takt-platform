"""New closed form proposals. Never publish or start an application process."""
import json
from fastapi import HTTPException
from . import forms as fm
from .db import Form


def require(user):
    from .agent import require as module_access
    module_access(user, 'forms')


def normalize(user, raw):
    require(user)
    title = raw.get('title')
    fields = raw.get('fields')
    if not isinstance(title, str) or not 3 <= len(title.strip()) <= 255:
        raise ValueError('Bitte einen Formulartitel mit 3 bis 255 Zeichen angeben.')
    if not isinstance(fields, list) or not 1 <= len(fields) <= 30:
        raise ValueError('Der Formularentwurf benötigt 1 bis 30 konkrete Fragen.')
    safe = []
    for field in fields:
        if not isinstance(field, dict) or field.get('type') not in ('short', 'long', 'date', 'time', 'number', 'yesno'):
            raise ValueError('Dieser Fragetyp ist im Agenten-Entwurf noch nicht unterstützt. Bitte im Baukasten ergänzen.')
        label = field.get('title')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 200:
            raise ValueError('Jede Frage benötigt eine eindeutige Bezeichnung.')
        if type(field.get('required', False)) is not bool:
            raise ValueError('Pflichtangaben müssen ausdrücklich als true oder false angegeben werden.')
        safe.append(dict(id=field.get('id') if isinstance(field.get('id'), str) else fm.new_id(), type=field['type'], title=label.strip(), required=field.get('required', False)))
    items = fm.clean_schema(safe)
    if len(items) != len(safe):
        raise ValueError('Die vorgeschlagenen Formularfragen sind ungültig.')
    return dict(tool='create_form', title=title.strip(), fields=items)


def preview(action):
    return ('Internen Formularentwurf erstellen: ' + action['title'] + '\nGeschlossen, ohne öffentlichen Link und ohne Antworten. Fragen:\n' +
            '\n'.join(f"{i}. {f['title']} ({f['type']}; {'Pflicht' if f['required'] else 'optional'})" for i, f in enumerate(action['fields'], 1)))


def execute(db, user, action):
    validated = normalize(user, action)
    row = Form(owner_id=user.id, title=validated['title'], kind='survey', internal=True, active=False,
               public_token=None, schema_json=json.dumps(validated['fields'], ensure_ascii=False))
    db.add(row); db.flush()
    return dict(label=preview(validated), url=f'/forms/{row.id}', target_id=row.id)
