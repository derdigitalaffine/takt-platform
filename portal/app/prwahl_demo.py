"""Stateless fictional election examples. Never reads or writes production election tables."""
from datetime import date
from types import SimpleNamespace
from .prwahl import FORM_KINDS


def election():
    return SimpleNamespace(
        title="Musterwahl 2027 – Stadtverwaltung Sonnenfels",
        service_name="Stadtverwaltung Sonnenfels (fiktiv)",
        body_type="personalrat", election_day=date(2027, 4, 14),
    )


COMMON = {
    "board_members": "Lena Muster (Vorsitz), Tim Beispiel (Mitglied), Sara König (Mitglied und Schriftführung)",
    "location": "Rathaus Sonnenfels, Bürgerraum EG (fiktiv)",
    "reference": "Fiktiver Bestellungsbeschluss WV-01 vom 12.01.2027",
    "meeting": "Rathaus Sonnenfels, 14.04.2027, 17:00 Uhr (Beispiel)",
    "session": "Sitzung des fiktiven Wahlvorstands am 14.04.2027, 17:00–19:00 Uhr",
    "attendance": "Lena Muster, Tim Beispiel, Sara König (sämtliche Namen erfunden)",
    "agenda": "Begrüßung; Prüfung der Unterlagen; Beschluss; Unterschriften auf Papier",
    "resolution": "Fiktiver Wahlvorstandsbeschluss: Angaben wurden beispielhaft geprüft; rechtliche Verbindlichkeit besteht nicht.",
    "signatories": "Lena Muster, Tim Beispiel, Sara König – Originalunterschriften wären in einer echten Wahl erforderlich",
    "signatures": "Lena Muster, Tim Beispiel, Sara König – MUSTER, ohne Originalunterschriften",
    "seats": "7 Sitze (rein fiktive Annahme; gesetzliche Sitzverteilung nicht ermittelt)",
    "eligible_count": "248 Wahlberechtigte (reine Demonstrationszahl)",
    "groups": "248 Personen in der beispielhaften Beschäftigtenliste; Gruppenabgrenzung nicht rechtsgeprüft",
    "recipient": "Lena Muster (fiktive Person)",
    "recipients": "Lena Muster, Tim Beispiel, Sara König und weitere gewählte Beispielpersonen",
    "candidate": "Alex Beispiel (fiktive Person)",
    "group_name": "Fiktive gemeinsame Wahl – Gruppe nicht rechtsgeprüft",
    "candidates": "Alex Beispiel, Dana Muster, Chris Fiktion (Namen und Reihenfolge fiktiv)",
    "election": "Fiktive Personalratswahl Stadtverwaltung Sonnenfels, 14.04.2027",
    "received_on": "Muster-Eingangsvermerk: 10.03.2027, 12:00 Uhr",
    "published_on": "16.04.2027, fiktiver Aushang Rathaus Sonnenfels",
    "counted_on": "14.04.2027, Rathaus Sonnenfels, 17:00 Uhr (nur Beispiel)",
    "counting": "14.04.2027, 17:00 Uhr, Rathaus Sonnenfels (fiktiv)",
    "ballots": "196 abgegebene Papierstimmzettel; 6 ungültig; 190 gültig (Beispiel)",
    "totals": "248 Wahlberechtigte; 196 Wählende; 196 Stimmzettel; 6 ungültig; 190 gültig",
    "entries": "Liste Miteinander: 94; Liste Zukunft: 61; Liste Dialog: 35 (rein fiktiv)",
    "publication": "Muster-Aushang Rathaus Sonnenfels; zusätzlich interne Information als Entwurf, kein Versand",
    "handover": "Fiktive Übergabe der Wahlakten im verschlossenen Umschlag gegen Quittung",
    "signature": "MUSTER: Lena Muster, Sonnenfels (keine echte Unterschrift)",
}

KIND = {
    "board_notice": {"issued_on": "2027-01-12"},
    "seats_protocol": {"session_on": "27.01.2027, Rathaus Sonnenfels, 14:00 Uhr"},
    "election_notice": {
        "issued_on": "03.02.2027, Sonnenfels",
        "election_mode": "Fiktive gemeinsame Wahl; die rechtliche Zulässigkeit wurde nicht geprüft",
        "gender_distribution": "Fiktive Auswertung: 132 Frauen, 114 Männer, 2 divers/ohne Angabe; nur Demonstration",
        "electoral_roll": "Rathaus Sonnenfels; Einsichtsrechte und Fristen vor Echtnutzung juristisch prüfen",
        "objections": "Einspruch an den Wahlvorstand; Rechtsgrundlage und Frist im Echtverfahren prüfen",
        "nominations": "Einreichung im Rathaus; keine reale Abgabefrist durch dieses Muster festgelegt",
        "voting": "Fiktives Wahllokal im Rathaus, 14.04.2027; Briefwahlvorgaben gesondert prüfen",
    },
    "nomination": {
        "list_name": "Liste Miteinander (fiktiv)",
        "supporters": "Keine echten Unterstützungsunterschriften – Originalunterschriften sind separat erforderlich",
        "representative": "Alex Beispiel (fiktive Vertrauensperson)",
    },
    "candidate_consent": {"consent": "Fiktive Zustimmung für Anschauungszwecke; keine reale Kandidatur"},
    "extension": {
        "reason": "Reine Musterkonstellation; ein Nachfristtatbestand wurde rechtlich nicht geprüft",
        "deadline": "Nicht festgelegt – nur nach Rechtsprüfung einzutragen",
        "submission": "Fiktives Wahlvorstandsbüro im Rathaus Sonnenfels",
    },
    "accepted_lists": {
        "accepted": "Liste Miteinander; Liste Zukunft; Liste Dialog – fiktiv",
    },
    "board_minutes": {
        "decisions": "Einstimmige fiktive Musterbeschlüsse; tatsächliche Wahlvorstandsbeschlüsse erforderlich",
    },
    "count_protocol": {
        "cross_check": "Rechnerischer Abgleich: 94 + 61 + 35 = 190 gültige Stimmen; 190 + 6 = 196 Stimmzettel",
    },
    "appointment_invitation": {
        "meeting_on": "12.01.2027, Rathaus Sonnenfels, 09:00 Uhr",
        "legal_basis": "LPersVG RLP – konkrete Zuständigkeit für echte Bestellung prüfen",
    },
    "appointment_resolution": {
        "members": COMMON["board_members"],
        "chair": "Lena Muster (fiktiv)",
        "notification": "Fiktive interne Mitteilung; kein tatsächlicher Versand",
    },
    "voter_roll_check": {
        "source": "Synthetischer Datensatz mit 248 fiktiven Beschäftigten, Stand 27.01.2027",
        "corrections": "Keine realen Beschäftigtendaten, Einsprüche oder Gesundheitsinformationen enthalten",
        "access": "Beispielhafte Einsicht im Wahlvorstandsbüro; rechtliche Anforderungen prüfen",
        "decision": "Mustervermerk WV-02; keine rechtliche Feststellung",
    },
    "ballot_material": {
        "postal": "Briefwahlunterlagen ausschließlich als Muster; keine Empfänger- oder Versanddaten",
        "helpers": "Tim Beispiel, Sara König; erforderliche Unterweisung beispielhaft dokumentiert",
        "secrecy": "Wahlkabine, verschlossene Urne, gesicherter Transport; keine Online-Stimmabgabe",
    },
    "count_reconciliation": {
        "ties": "Keine Gleichstände im fiktiven Datensatz; Losentscheidungen nicht simuliert",
    },
    "elected_notification": {
        "rights": "Rechte, Annahme-/Ablehnungsfristen und Rechtsbehelfe müssen vor realer Zustellung geprüft werden",
        "delivery": "Nur fiktive Übergabe, nicht versendet",
    },
    "constitution_invitation": {
        "inviter": "Lena Muster, Wahlvorstandsvorsitz (fiktiv)",
    },
    "constitution_minutes": {
        "chair_election": "Fiktive Wahl des Vorsitzes; keine rechtsverbindliche Feststellung",
        "further_elections": "Keine weiteren echten Wahlen dokumentiert",
    },
    "archive_handover": {
        "from_to": "Lena Muster, fiktiver Wahlvorstand, an Alex Beispiel, fiktiver Personalrat",
        "inventory": "Fiktives Verzeichnis: Beschluss, Wahlausschreiben, Niederschrift, Ergebnis, Anlagen",
        "handover_on": "30.04.2027, Rathaus Sonnenfels",
    },
    "result_notice": {
        "determination": "Fiktive Feststellung nach Papierauszählung am 14.04.2027; keine amtliche Feststellung",
        "elected": "Alex Beispiel, Dana Muster, Chris Fiktion (fiktive Namen; keine echte Sitzberechnung)",
        "public_details": "Nur fiktive Namens- und Ergebnisdaten; Zulässigkeit im Echtverfahren prüfen",
    },
}


def sample_values(kind: str) -> dict[str, str]:
    if kind not in FORM_KINDS:
        raise KeyError(kind)
    values = {}
    overrides = KIND.get(kind, {})
    for field, label, field_type in FORM_KINDS[kind][2]:
        values[field] = (overrides.get(field) or COMMON.get(field) or
                         ("2027-02-03" if field_type == "date" else
                          f"Fiktives Beispiel: {label}. Vor Verwendung rechtlich und fachlich prüfen."))
    return values
