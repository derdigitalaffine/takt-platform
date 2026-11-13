"""Conservative prefill of election *drafts* from already scoped, known facts.

Never infer eligible voters, deadlines, seat allocations, election results,
legal validity or publication solely from platform data.
"""
from .prwahl import FORM_KINDS


BOARD_ROLES = {"chair": "Vorsitz", "member": "Mitglied", "clerk": "Schriftführung"}


def prefill_fields(election, kind, *, mandates=(), events=(), rounds=()):
    if kind not in FORM_KINDS:
        raise KeyError(kind)
    values, sources = {}, {}
    allowed = {key for key, _, _ in FORM_KINDS[kind][2]}

    def put(key, value, source):
        if key in allowed and value and str(value).strip():
            values[key] = str(value)
            sources[key] = source

    members = [(mandate, person) for mandate, person in mandates
               if mandate.role in BOARD_ROLES and getattr(person, "active", False)]
    members.sort(key=lambda item: (list(BOARD_ROLES).index(item[0].role), item[1].name.casefold()))
    team = "; ".join(f"{person.name} ({BOARD_ROLES[mandate.role]}; Bestellung gesondert prüfen)"
                     for mandate, person in members)
    chair = next((person.name for mandate, person in members if mandate.role == "chair"), "")
    chair_reference = next((m.appointment_reference for m, p in members
                            if m.role == "chair" and m.appointment_reference), "")
    day = election.election_day.strftime("%d.%m.%Y") if election.election_day else ""
    place = (election.election_location or "").strip()
    vote = ", ".join(filter(None, (day, place)))
    event_by_kind = {}
    for event in events:
        if event.status == "planned" and event.kind not in event_by_kind:
            event_by_kind[event.kind] = event

    def describe_event(event_kind):
        event = event_by_kind.get(event_kind)
        if not event:
            return ""
        from .prwahl_schedule import display_local
        return ", ".join(filter(None, (display_local(event.starts_at), event.location)))

    if kind == "board_notice":
        put("board_members", team, "Zugeordnete TAKT-Fachmandate, keine nachgewiesene Bestellung")
        put("reference", chair_reference, "Im TAKT-Mandat gespeicherter Benennungsnachweis")
    elif kind == "appointment_resolution":
        put("members", team, "TAKT-Fachmandate, rechtliche Bestellung offen")
        put("chair", chair, "Zugewiesener Wahlvorstandsvorsitz")
    elif kind == "board_minutes":
        put("attendance", team, "Fachmandate – tatsächliche Anwesenheit prüfen")
        put("session", describe_event("board"), "Geplanter Wahlvorstandstermin")
    elif kind in {"seats_protocol", "appointment_invitation"}:
        field = "session_on" if kind == "seats_protocol" else "meeting_on"
        put(field, describe_event("board"), "Geplanter Wahlvorstandstermin")
    elif kind == "election_notice":
        put("voting", "Geplanter Wahltag und Wahlort: " + vote if vote else "",
            "Planungsdaten der Wahl – Wahlzeit und Bekanntmachung prüfen")
        put("counting", describe_event("count"), "Geplanter Auszählungstermin")
    elif kind == "ballot_material":
        put("location", vote, "Wahltag und Wahlort aus Wahl-Stammdaten")
    elif kind == "constitution_invitation":
        put("meeting", describe_event("constitution"), "Geplanter Termin der konstituierenden Sitzung")
    elif kind == "constitution_minutes":
        put("meeting", describe_event("constitution"), "Geplanter Termin – tatsächlichen Verlauf prüfen")
    elif kind == "elected_notification":
        put("election", election.title, "Bezeichnung des Wahl-Arbeitsbereichs")

    if kind in {"count_protocol", "count_reconciliation"}:
        confirmed = [row for row in rounds if row.status == "confirmed"]
        if confirmed:
            lines = [f"{r.group_name}: {r.ballots_cast} Stimmzettel, "
                     f"{r.invalid_ballots} ungültig, {r.ballots_cast-r.invalid_ballots} gültig "
                     "(manuell bestätigt, fachliche Gegenprüfung erforderlich)" for r in confirmed]
            put("ballots" if kind == "count_protocol" else "totals", "\n".join(lines),
                "Manuell bestätigte aggregierte Auszählung, keine amtliche Ergebnisfeststellung")
    return values, sources
