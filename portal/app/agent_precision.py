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
    if re.search(r'terminumfrage',prompt,re.I):
        text += 'Terminumfragen sind create_survey mit record_kind=poll und konkreten Alternativterminen, keine freien Kalendertermine. '
    if re.search(r'wortwolke|quiz|live.umfrage',prompt,re.I):
        text += 'Wortwolke und Quiz gehören zu create_survey mit record_kind=live_poll. Quizlösungen müssen ausdrücklich mit Antwortnummern ab 1 angegeben werden. '
    if re.search(r'formular', prompt, re.I) and re.search(r'geburtstag', prompt, re.I):
        text += ('Bei einer Geburtstagsliste für die Belegschaft nur Namen, Tag und Monat abfragen, '
                 'wenn kein Geburtsjahr verlangt ist. Tag als Zahl 1–31, Monat als Auswahlliste. '
                 'Nur ausdrücklich gewünschte weitere personenbezogene Felder aufnehmen. ')
    if re.search(r'aktenzeichen|antrag|anträge', prompt, re.I):
        text += ('Eingegangene Anträge sind Vorgänge, keine Prozessvorlagen. Zuerst nach exaktem '
                 'Aktenzeichen suchen. Für Genehmigung, Ablehnung und Erledigung eines aktiven '
                 'Arbeitsschritts application_step mit step.id und den angebotenen operation-Werten wählen. ')
    return text


def focus_modules(prompt):
    """Reduce the schema shown to a small model; this is never an authorization check."""
    patterns = {
        'tasks': r'aufgabe|checkliste|fällig|priorit',
        'anliegen': r'anliegen|mangel|mängel|büromaterial|büromöbel|bürost[üu]hl|druckerpapier|kopierpapier|toner|störung|defekt',
        'surveys': r'umfrage|abstimmung|wortwolke|doodle|quiz',
        'applications': r'\bantr(?:ag|äge|ägen|ags\w*)\b|aktenzeichen|sachbearbeitung|nachforderung',
        'forms': r'formular', 'calendars': r'kalender|termin|besprechung',
        'dms': r'\bdms\b|wissensakte', 'processes': r'prozess',
        'leave': r'urlaub|urlaubsantrag|urlaubsplanung',
    }
    selected = {key for key, pattern in patterns.items() if re.search(pattern, prompt, re.I)}
    if re.search(r'terminumfrage',prompt,re.I) and not re.search(r'kalender|einzeltermin',prompt,re.I):
        selected.discard('calendars')
    return selected or None


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
