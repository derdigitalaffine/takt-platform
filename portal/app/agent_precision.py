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
