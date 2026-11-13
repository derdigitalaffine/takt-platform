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
