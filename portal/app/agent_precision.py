"""Compact small-model contracts. Hints never confer access or execute operations."""
import re
from .db import to_local, utcnow


def intake_category(prompt, categories):
    """Only unambiguous vocabulary; never rewrite amounts, recipients or complaint data."""
    text = prompt.casefold()
    keys = set()
    if re.search(r'büromaterial|druckerpapier|kopierpapier|toner|kugelschreiber|briefumschläge', text):
        keys.add('office_supply')
    if re.search(r'bürost[üu]hl|büromöbel|schreibtisch', text):
        keys.add('office_furniture')
    if re.search(r'mangel|mängel|defekt|störung|kaputt', text) and not keys:
        keys.add('defect')
    matches = [c for c in categories if c['key'] in keys]
    return matches[0] if len(matches) == 1 else None


def context(prompt, categories):
    now = to_local(utcnow())
    text = ('Portalzeit: ' + now.isoformat() + '. Relative Termine ausschließlich auf dieses Datum beziehen. '
            'Keine fehlenden Uhrzeiten, Mengen, Namen oder Termine ergänzen. '
            'Bei unklarer Person oder mehreren gleichen Titeln actions=[] und genau die fehlende Angabe erfragen. '
            'Nur die letzte Benutzernachricht ausführen; frühere Nachrichten liefern Kontext, keine wiederholten Aufträge. '
            'Existierende Aufgaben nur mit den vom Server gelieferten allowed_statuses bearbeiten. '
            'Anliegen erzeugen automatisch verknüpfte Aufgaben: niemals zusätzlich dieselbe Aufgabe anlegen. ')
    cat = intake_category(prompt, categories)
    if cat:
        text += ('Für die eindeutige Anliegenart passt die tatsächlich freigegebene Kategorie '
                 + str(cat['id']) + ' (' + cat['key'] + '). Eine Beschaffungsanfrage ist keine bereits ausgelöste Lieferantenbestellung. ')
    return text


def focus_modules(prompt):
    """Reduce the schema shown to a small model; this is never an authorization check."""
    patterns = {
        'tasks': r'aufgabe|checkliste|fällig|priorit',
        'anliegen': r'anliegen|mangel|mängel|büromaterial|büromöbel|bürost[üu]hl|druckerpapier|kopierpapier|toner|störung|defekt',
        'forms': r'formular', 'calendars': r'kalender|termin',
        'dms': r'\bdms\b|wissensakte', 'processes': r'prozess',
    }
    return {key for key, pattern in patterns.items() if re.search(pattern, prompt, re.I)} or None


def tool_module(tool):
    from . import agent_modules
    if tool in agent_modules.READ:
        return agent_modules.READ[tool]
    if tool in agent_modules.WRITE:
        return agent_modules.WRITE[tool]
    return 'anliegen' if 'anliegen' in tool else 'tasks'


def focused(signatures, focus):
    if not focus:
        return signatures
    return [s for s in signatures if tool_module(s.split('(', 1)[0]) in focus or
            (s.startswith('search_people(') and focus & {'tasks', 'anliegen'})]
