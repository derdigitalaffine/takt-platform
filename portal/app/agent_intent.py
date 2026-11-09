"""Conservative routing: a normal question is not a TAKT mutation request.

Only clearly scoped, intentional TAKT operations enter the JSON tool planner.
Ambiguous messages remain conversational; this is not an authorization layer.
The tool registry and module permissions enforce the authoritative ACL.
"""
import re

_QUESTION = re.compile(
    r"^\s*(?:was\s+(?:ist|sind|bedeutet|heißt)|wer\s+|wie\s+"
    r"(?:geht|funktioniert|heißt|ist|kann|wird|würde)|warum\s+|"
    r"wieso\s+|wozu\s+|wann\s+|was\s+(?:kann|heißt|bedeutet)|"
    r"erklär(?:e|st du)?\s+(?:mir\s+)?|definiere\s+|"
    r"ich\s+(?:habe|möchte)\s+eine\s+frage)",
    re.I,
)
_DOMAIN = re.compile(
    r"\b(?:aufgab\w*|todo\w*|anliegen|mängel|mangel|beschaffung|"
    r"büromaterial|büromöbel|bestellung\w*|formular\w*|"
    r"kalender\w*|termin\w*|besprechung\w*|akte\w*|"
    r"dms|vorgang\w*|prozess\w*|status|priorität|"
    r"zuständigkeit\w*|kolleg\w*)\b",
    re.I,
)
_ACTION = re.compile(
    r"\b(?:erstell\w*|anleg\w*|lege\b|leg\b|"
    r"trag\w*\s+ein|eintragen|änder\w*|bearbeit\w*|"
    r"setz\w*|weise\w*|zuweis\w*|verschieb\w*|"
    r"kopier\w*|lösch\w*|meld\w*|erfass\w*|"
    r"plan\w*|organisier\w*|aktualisier\w*|"
    r"priorisier\w*|vorbereit\w*|start\w*|markier\w*|abschließ\w*|"
    r"als\s+(?:erledigt|in\s+bearbeitung)\s+markieren)\b",
    re.I,
)
_READ = re.compile(
    r"\b(?:suche|such|finde|find|zeig\w*|list\w*|"
    r"welche|was\s+sind|habe\s+ich|gibt\s+es|"
    r"offene\s+aufgaben|mir\s+zugewiesen|fällig)\b",
    re.I,
)
_NAV = re.compile(
    r"^\s*(?:(?:bitte\s+)?(?:öffne|bringe?\s+mich\s+zu|"
    r"navigiere\s+zu|geh(?:e)?\s+zu|wechsle\s+(?:zu|in))\s+)",
    re.I,
)
_FOLLOWUP = re.compile(
    r"^(?:welche\s+angaben\s+fehlen(?:\s+noch)?\??|"
    r"was\s+fehlt\s+noch\??|so\s+machen\b.*|"
    r"führe\s+(?:das|es)\s+(?:so\s+)?(?:aus|durch)\b.*)$",
    re.I,
)
_NAV_MODULES = (
    ("tasks", re.compile(r"\b(?:aufgaben|todo\w*)\b", re.I), "/aufgaben", "Aufgaben"),
    ("anliegen", re.compile(r"\b(?:anliegen|beschaffung\w*|bestellungen)\b", re.I), "/anliegen", "Interne Anliegen"),
    ("calendars", re.compile(r"\b(?:kalender|termine)\b", re.I), "/kalender?ansicht=termine", "Kalender"),
    ("forms", re.compile(r"\b(?:formular\w*)\b", re.I), "/forms", "Formulare"),
    ("dms", re.compile(r"\b(?:dms|dokumentenablage|akten)\b", re.I), "/dms", "Ablage"),
    ("processes", re.compile(r"\b(?:prozesse|prozessverwaltung)\b", re.I), "/processes", "Prozesse"),
)


def classify(prompt: str, *, has_work_context: bool = False) -> str:
    """'chat', 'navigate' or 'operate'; false positives must stay in chat."""
    value = (prompt or "").strip()
    if _FOLLOWUP.fullmatch(value):
        return "operate" if has_work_context else "chat"
    if _NAV.search(value) and _DOMAIN.search(value):
        return "navigate"
    if _QUESTION.search(value):
        return "chat"
    # Explicit native form/task headings in operator workflows are requests
    # to prepare a TAKT action even if the suffix is a terse description.
    if re.match(r"^(?:internes\\s+anliegen|anliegen\\s+\\w+|aufgabe\\s+\\w+|routing\\s+\\w+)\\s*:", value, re.I):
        return "operate"
    if _ACTION.search(value) and (_DOMAIN.search(value) or
                                  re.search(r"\b(?:schritte\s+vorbereiten|auftrag)\b", value, re.I)):
        return "operate"
    if _READ.search(value) and _DOMAIN.search(value):
        return "operate"
    if re.search(r"\b(?:neuer\s+unabhängiger\s+auftrag|schritte\s+vorbereiten)\b", value, re.I):
        return "operate"
    return "chat"


def navigation(prompt: str, user):
    """Return a *link suggestion*, never an instruction to change browser URL."""
    from . import agent
    if classify(prompt) != "navigate":
        return None
    for module, pattern, url, label in _NAV_MODULES:
        if pattern.search(prompt):
            if not agent.allowed(user, module):
                return None
            return {"url": url, "label": label}
    return None
