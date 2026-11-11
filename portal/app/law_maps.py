"""Versioned spatial references for laws; every linked object keeps its own access rules."""
import json

from . import maps
from .db import LawAttachment, UserMap


def state(law):
    try:
        data = json.loads(law.map_json or '{}')
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def clean(db, law, user, data):
    from .routes_maps import can_open_map
    out = {}
    for field, model in [('map_id', UserMap), ('attachment_id', LawAttachment)]:
        raw = str(data.get(field) or '').strip()
        if not raw:
            continue
        if not (raw.isascii() and raw.isdecimal() and len(raw) <= 18):
            raise ValueError('Bitte eine gültige Karte bzw. Anlage auswählen.')
        obj = db.get(model, int(raw))
        if obj is None or (field == 'map_id' and not can_open_map(obj, user)) or (field == 'attachment_id' and obj.law_id != law.id):
            raise ValueError('Die gewählte Karte oder Anlage ist nicht zugänglich.')
        out[field] = obj.id
    raw = str(data.get('geometry') or '').strip()
    if raw:
        if len(raw) > 200_000:
            raise ValueError('Der Geltungsbereich ist zu groß.')
        try:
            geometry = maps.clean_geometry(json.loads(raw))
        except (ValueError, TypeError):
            geometry = None
        if geometry is None or geometry['type'] != 'Polygon':
            raise ValueError('Bitte einen gültigen Geltungsbereich als Fläche zeichnen.')
        out['geometry'] = geometry
    if out.get('attachment_id') and not (out.get('geometry') or out.get('map_id')):
        raise ValueError('Für die PDF-Anlage bitte einen Geltungsbereich oder eine Karte zuordnen.')
    return out


def available_map(db, data, user):
    from .routes_maps import can_open_map
    row = db.get(UserMap, data.get('map_id')) if data.get('map_id') else None
    if row and (row.public_token or (user and can_open_map(row, user))):
        return row
    return None


def available_attachment(db, law, data, user):
    row = db.get(LawAttachment, data.get('attachment_id')) if data.get('attachment_id') else None
    return row if row and row.law_id == law.id and (not row.internal or user is not None) else None
