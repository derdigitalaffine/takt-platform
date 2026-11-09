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


# Tool invocation is opt-in by user intent, NOT the default for every message.
# Deliberately conservative: an unsure classification must get a normal chat
# reply, not a fabricated plan or a false claim that something was changed.
_ACTION_VERB = re.compile(
    r"\b(?:erstelle|erstell|anlegen|lege|füge|hinzufügen|trage|eintragen|"
    r"ändere|änder|bearbeite|aktualisiere|verschiebe|kopiere|dupliziere|"
    r"weise|zuweisen|zuordnen|setze|markiere|erledige|lösche|lösch|"
    r"suche|finde|öffne|zeige|navigiere|bring|leite|plane|buche|"
    r"starte|beende|schließe|sende)\b", re.I)
_ACTION_OBJECT = re.compile(
    r"\b(?:aufgab\w*|anliegen|formular\w*|kalender|termin\w*|"
    r"prozess\w*|akten|akte|dms|büromaterial|büromöbel|"
    r"bestellung\w*|status|zuständigkeit|priorität|"
    r"organisation\w*|bereich\w*)\b", re.I)
_ACTION_REQUEST = re.compile(
    r"\b(?:bitte|kannst du|könntest du|würdest du|ich möchte|ich will|"
    r"ich brauche|wir brauchen|hilf mir|mach|machst du)\b", re.I)
_EXPLANATION = re.compile(
    r"^\s*(?:was|wer|wie|warum|wieso|weshalb|woher|wofür|"
    r"bedeutet|erkläre|erklär|definiere|beschreibe|"
    r"ist|sind|kann man|darf man)\b", re.I)


def needs_tools(prompt: str) -> bool:
    """Only deliberate TAKT operations/searches enter the JSON tool planner.

    Generic knowledge questions (including a question about a TAKT module)
    use conversational LLM completion. No AI guess may grant write access.
    """
    value = (prompt or "").strip()
    if not value:
        return False
    if _EXPLANATION.search(value):
        return False
    if _ACTION_VERB.search(value) and _ACTION_OBJECT.search(value):
        return True
    # "Meine offenen Aufgaben" and similar scoped in-app lookups.
    if _ACTION_OBJECT.search(value) and re.search(
        r"\b(?:meine|meinen|mir zugewiesen|bei mir|offene|überfällige)\b",
        value, re.I
    ) and not value.endswith("?"):
        return True
    return False
