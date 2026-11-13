"""Non-binding RLP election date suggestions with transparent dependencies.

Source: WOLPersVG RLP §§ 6(1), 7(2), as checked 2026-11-13.
No holiday/business-day inference and no legal release is performed here.
"""
from datetime import date, timedelta


def suggestions(election, *, notice_effective_on=None):
    rows = []
    first = election.election_day
    last = election.election_end_day or first
    if not first or not last or last < first:
        return rows
    rows.append({
        "code": "vote", "kind": "ballot", "on": first,
        "title": "Geplanter erster Wahltag",
        "rule": "Wahl-Stammdaten",
        "detail": "Wahlbeginn, Wahlzeiten und Wahllokal durch den Wahlvorstand festlegen.",
        "legal": False,
    })
    # Only calculate standard local staff council deadlines: other election
    # bodies/exceptional variants require a separately reviewed ruleset.
    if election.body_type == "personalrat":
        rows.insert(0, {
            "code": "notice", "kind": "notice", "on": last - timedelta(weeks=6),
            "title": "Orientierung: spätester Erlass des Wahlausschreibens",
            "rule": "§ 6 Abs. 1 WOLPersVG RLP – spätestens sechs Wochen vor dem letzten Wahltag",
            "detail": "Erst nach Ablauf der Frist nach § 4 Abs. 1; Unterschriften, Aushang und Varianten prüfen. Der Wahlvorstand muss die tatsächliche Frist bestätigen.",
            "legal": True,
        })
        if isinstance(notice_effective_on, date):
            rows.append({
                "code": "nominations", "kind": "nomination",
                "on": notice_effective_on + timedelta(days=18),
                "title": "Orientierung: Ende der Vorschlagsfrist ohne Fristbeginn-Verschiebung",
                "rule": "§ 7 Abs. 2 WOLPersVG RLP – 18 Kalendertage ab dem Folgetag des Erlasses",
                "detail": "Nur gültig, wenn der tatsächliche Erlasstag dokumentiert und kein späterer Fristbeginn festgesetzt wurde; mögliche Verschiebung bis zu drei Arbeitstagen und Uhrzeit separat rechtlich prüfen.",
                "legal": True,
            })
    return sorted(rows, key=lambda row: (row["on"], row["code"]))


def diagnose(election, *, notice_effective_on=None):
    """Non-binding, actionable consistency hints for the protected calendar.

    Returns only facts that can be grounded in the election's own data. The
    warnings are not decisions on the legal validity of an election.
    """
    problems = []
    first = election.election_day
    last = election.election_end_day or first
    if not first:
        return [{"kind": "info", "title": "Wahltag fehlt",
                 "detail": "Ersten und gegebenenfalls letzten Wahltag in den Wahldaten eintragen."}]
    if last < first:
        return [{"kind": "warning", "title": "Wahlzeitraum widersprüchlich",
                 "detail": "Der letzte Wahltag liegt vor dem ersten. Stammdaten korrigieren."}]
    if election.body_type != "personalrat":
        problems.append({"kind": "info", "title": "Sonderwahlkörper: juristische Fristenprüfung",
                         "detail": "Für diesen Wahlkörper liegen keine freigegebenen automatischen Fristregeln vor."})
        return problems
    latest_notice = last - timedelta(days=42)
    if notice_effective_on is None:
        problems.append({"kind": "info", "title": "Erlass des Wahlausschreibens nicht dokumentiert",
                         "detail": "Den tatsächlichen Erlasstag erst nach Beschluss und Bekanntgabe im Wahlfahrplan nachweisen; Vorschlagsfrist erst dann berechnen."})
    else:
        if notice_effective_on > latest_notice:
            problems.append({"kind": "warning", "title": "Erlasstag später als die Sechswochen-Orientierung",
                             "detail": "Den in der Wahlakte dokumentierten Erlasstag mit § 6 Abs. 1 WOLPersVG und eventuellen Sonderregeln dringend juristisch prüfen."})
        if notice_effective_on >= first:
            problems.append({"kind": "warning", "title": "Erlass nicht vor der Wahl",
                             "detail": "Wahlausschreiben und tatsächlichen Wahlbeginn abgleichen. Es wird keine automatische Freigabe erteilt."})
        elif notice_effective_on + timedelta(days=18) >= first:
            problems.append({"kind": "warning", "title": "Vorschlagsfrist reicht bis an die Stimmabgabe",
                             "detail": "Die rechnerische Standardfrist und den Wahltermin unabhängig überprüfen; Sonderfälle und Fristbeginn-Verschiebung bleiben offen."})
    return problems


def mark_existing(proposals, events):
    """Identify already planned events on the proposal's local calendar day."""
    from datetime import timezone
    from .prwahl_schedule import TZ
    candidates = {(event.kind, event.starts_at.replace(tzinfo=timezone.utc).astimezone(TZ).date())
                  for event in events if event.status == "planned"}
    return [{**row, "already_planned": (row["kind"], row["on"]) in candidates}
            for row in proposals]
