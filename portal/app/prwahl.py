"""Policy and document definitions for RLP paper-election preparation.

Deliberately no statutory deadlines, binding seat allocations or approval of rules
without a jurisdiction-specific, independently reviewed legal rule pack.
"""
import json
import re
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select

from .db import User, Organization
from .organization import active_path
from .prwahl_models import PRElection, PRMandate, PRTask, PRDocument, PRAudit
from .security import encrypt, decrypt

BODY_TYPES = {
    "personalrat": "Örtlicher Personalrat",
    "gesamtpersonalrat": "Gesamtpersonalrat",
    "bezirkspersonalrat": "Bezirkspersonalrat",
    "hauptpersonalrat": "Hauptpersonalrat",
    "jav": "Jugend- und Auszubildendenvertretung",
}
ROLES = {
    "coordinator": "Organisation / Einrichtung",
    "chair": "Vorsitz des Wahlvorstands",
    "member": "Mitglied des Wahlvorstands",
    "clerk": "Schriftführung",
    "legal": "Fachjuristische Prüfung",
    "auditor": "Eingeschränkte Prüfung",
}
EDIT_ROLES = {"coordinator", "chair", "member", "clerk"}
INITIAL_TASKS = (
    ("Bestellung des Wahlvorstands nachweisen", "appointment", "LPersVG / WOLPersVG"),
    ("Dienststelle, Wahlkörper und Wahlart fachlich prüfen", "scope", "LPersVG"),
    ("Wahlberechtigtenverzeichnis rechtssicher prüfen", "electors", "§§ 2–3 WOLPersVG"),
    ("Sitz- und Gruppenverteilung durch Wahlvorstand feststellen", "seats", "§ 5 WOLPersVG"),
    ("Wahlausschreiben beschließen, unterzeichnen und bekanntgeben", "notice", "§ 6 WOLPersVG"),
    ("Wahlvorschläge und Originalunterschriften prüfen", "nominations", "§§ 7–13 WOLPersVG"),
    ("Wahlmaterial und ggf. schriftliche Stimmabgabe organisieren", "material", "WOLPersVG"),
    ("Papierwahl durchführen und Wahlgeheimnis sicherstellen", "voting", "LPersVG / WOLPersVG"),
    ("Ergebnis auszählen und Wahlvorstandsbeschluss dokumentieren", "count", "WOLPersVG"),
    ("Ergebnis bekanntmachen und Wahlakten geordnet übergeben", "close", "WOLPersVG"),
)
# (label, help, fields): keys are strictly allowlisted, so metadata cannot smuggle
# input fields into PDF, print output, logs, other modules or the audit trail.
FORM_KINDS = {
    "board_notice": ("Bekanntmachung des Wahlvorstands", "Muster 1 · § 1 Abs. 5 WOLPersVG", (
        ("issued_on", "Datum der Bekanntmachung", "date"),
        ("board_members", "Mitglieder und Funktionen des Wahlvorstands", "multiline"),
        ("location", "Ort des Aushangs / Bekanntgabekanal", "text"),
        ("reference", "Bestellungsbeschluss / Nachweis", "text"),
    )),
    "seats_protocol": ("Niederschrift der Sitz- und Gruppenverteilung", "Muster 2 · §§ 5 und 14 WOLPersVG", (
        ("session_on", "Datum, Ort und Beginn der Sitzung", "text"),
        ("eligible_count", "Zahl der Wahlberechtigten und berücksichtigte Gruppen", "multiline"),
        ("seats", "Vom Wahlvorstand ermittelte Sitzverteilung mit Rechenweg", "multiline"),
        ("resolution", "Wortlaut des Beschlusses", "multiline"),
        ("signatories", "Mitglieder zur Unterzeichnung", "multiline"),
    )),
    "election_notice": ("Wahlausschreiben", "Muster 3a / 3b · § 6 WOLPersVG", (
        ("issued_on", "Erlassdatum und Ort", "text"),
        ("election_mode", "Gruppenwahl oder gemeinsame Wahl; Begründung", "text"),
        ("seats", "Mitgliederzahl und Aufteilung auf Gruppen", "multiline"),
        ("gender_distribution", "Anteile der Geschlechter (gesamt und Gruppen)", "multiline"),
        ("electoral_roll", "Ort / Zeitraum der Einsichtnahme in das Wählerverzeichnis und Rechtsvorschriften", "multiline"),
        ("objections", "Einspruchsweg und Frist mit Rechtsgrundlage", "multiline"),
        ("nominations", "Wahlvorschläge: Einreichungsort und Frist", "multiline"),
        ("voting", "Wahlort, Wahlzeiten und Regeln zur schriftlichen Stimmabgabe", "multiline"),
        ("counting", "Ort und Zeitpunkt der Stimmenauszählung", "text"),
        ("publication", "Bekanntgabestellen und Bekanntgabeverfahren", "multiline"),
    )),
    "nomination": ("Wahlvorschlag", "Muster 5a / 5b · § 7 WOLPersVG", (
        ("list_name", "Kennwort / Bezeichnung des Wahlvorschlags", "text"),
        ("group_name", "Gruppe / gemeinsame Wahl", "text"),
        ("candidates", "Bewerbende mit vorgeschriebenen Angaben in Reihenfolge", "multiline"),
        ("supporters", "Unterstützungsunterschriften – ausschließlich auf Originalbogen", "multiline"),
        ("representative", "Vertrauensperson / Ansprechpartner", "text"),
        ("received_on", "Eingangsvermerk des Wahlvorstands", "text"),
    )),
    "candidate_consent": ("Zustimmung zur Kandidatur", "Muster 6 · § 9 WOLPersVG", (
        ("candidate", "Name der kandidierenden Person", "text"),
        ("group_name", "Gruppe / Wahlvorschlag", "text"),
        ("consent", "Erklärung zur Kandidatur", "multiline"),
        ("signature", "Ort, Datum und handschriftliche Unterschrift (auf Papier)", "text"),
    )),
    "extension": ("Bekanntmachung einer Nachfrist", "Muster 4a / 4b · § 11 WOLPersVG", (
        ("reason", "Voraussetzung der Nachfrist / Beschluss", "multiline"),
        ("deadline", "Fristende (rechtlich geprüft, kein automatisch errechnetes Datum)", "text"),
        ("submission", "Einreichungsort und Form", "multiline"),
        ("publication", "Bekanntmachung und Nachweis", "multiline"),
    )),
    "accepted_lists": ("Bekanntgabe gültiger Wahlvorschläge", "Muster 7a / 7b · §§ 12–13 WOLPersVG", (
        ("accepted", "Zugelassene Listen oder Personen – ohne Unterzeichnernamen", "multiline"),
        ("resolution", "Entscheidungen des Wahlvorstands / Begründung", "multiline"),
        ("published_on", "Datum und Ort der Bekanntgabe", "text"),
    )),
    "board_minutes": ("Wahlvorstand – Sitzungsniederschrift", "§ 14 WOLPersVG", (
        ("session", "Datum, Ort, Beginn und Ende", "text"),
        ("attendance", "Anwesende Mitglieder und weitere zulässige Beteiligte", "multiline"),
        ("agenda", "Tagesordnung", "multiline"),
        ("decisions", "Beschlüsse im Wortlaut und Abstimmung", "multiline"),
        ("signatories", "Alle nach der Wahlordnung erforderlichen Unterschriften", "multiline"),
    )),
    "count_protocol": ("Niederschrift der Papierauszählung", "WOLPersVG · Ergebnisfeststellung", (
        ("counted_on", "Tag, Ort und Zeit der Auszählung", "text"),
        ("ballots", "Zahl abgegebener / gültiger / ungültiger Stimmzettel", "multiline"),
        ("totals", "Anonymisierte Stimmenzahlen und Rechenweg", "multiline"),
        ("cross_check", "Unabhängige Gegenprüfung / Abweichungen", "multiline"),
        ("resolution", "Wahlvorstandsbeschluss und Unterschriften", "multiline"),
    )),
    "appointment_invitation": ("Einladung zur Bestellung des Wahlvorstands", "LPersVG · Bestellung und Einladung", (
        ("recipient", "Adressaten / zuständiges Gremium", "multiline"),
        ("meeting_on", "Termin, Ort und Beginn", "text"),
        ("agenda", "Tagesordnung und Beschlussgegenstand", "multiline"),
        ("legal_basis", "Rechtsgrundlage und Zuständigkeit (fachlich geprüft)", "text"),
        ("signature", "Einladende Person / Unterschrift", "text"),
    )),
    "appointment_resolution": ("Bestellung des Wahlvorstands", "LPersVG · Bestellungsbeschluss", (
        ("meeting", "Beschlussorgan, Datum, Sitzungsangaben", "text"),
        ("members", "Mitglieder, Ersatzmitglieder und Gruppen", "multiline"),
        ("chair", "Bestellte vorsitzende Person", "text"),
        ("resolution", "Beschlusswortlaut und Abstimmungsergebnis", "multiline"),
        ("notification", "Unterrichtung und Bekanntgabe", "multiline"),
        ("signatories", "Originalunterschriften", "multiline"),
    )),
    "voter_roll_check": ("Prüfvermerk Wählerverzeichnis", "WOLPersVG · Prüfung des Verzeichnisses", (
        ("source", "Herkunft und Stichtag der Ausgangsdaten", "text"),
        ("groups", "Gruppen und summarische Zahlen", "multiline"),
        ("corrections", "Prüfungen, Berichtigungen und Einsprüche (ohne vertrauliche Einzeldaten)", "multiline"),
        ("access", "Einsichtnahmemöglichkeit und Zugang", "multiline"),
        ("decision", "Beschluss und Dokumentationsverweis", "multiline"),
    )),
    "ballot_material": ("Material- und Wahllokalcheck", "WOLPersVG · Vorbereitung der Papierwahl", (
        ("location", "Wahllokale, Öffnungszeiten und Zugänglichkeit", "multiline"),
        ("ballots", "Stimmzettel: Druckfreigabe, Anzahl, sichere Lagerung", "multiline"),
        ("postal", "Schriftliche Stimmabgabe, Unterlagen, Eingangsorganisation", "multiline"),
        ("helpers", "Wahlhelferinnen und Wahlhelfer, Unterweisung", "multiline"),
        ("secrecy", "Wahlgeheimnis, Urne, Wahlkabine und Übergabeprotokolle", "multiline"),
    )),
    "count_reconciliation": ("Prüfbogen öffentliche Stimmenauszählung", "WOLPersVG · Öffentliche Auszählung", (
        ("meeting", "Ort, Zeitpunkt, Öffentlichkeit und anwesender Wahlvorstand", "multiline"),
        ("totals", "Wahlberechtigte, Wählende, Stimmzettel und ungültige Stimmen", "multiline"),
        ("entries", "Listen- oder Personenstimmen und unabhängiger Abgleich", "multiline"),
        ("ties", "Gleichstände, Losentscheidungen und Sonderfälle (manuell)", "multiline"),
        ("signatures", "Wahlvorstandsbeschluss und Originalunterschriften", "multiline"),
    )),
    "elected_notification": ("Benachrichtigung der gewählten Mitglieder", "LPersVG / WOLPersVG · Wahlannahme", (
        ("recipient", "Gewähltes Mitglied", "text"),
        ("election", "Wahl, Feststellung und Sitz", "multiline"),
        ("rights", "Rechtsbelehrung und Annahme-/Ablehnungsfrist (fachlich geprüft)", "multiline"),
        ("delivery", "Zustellung und Nachweis", "multiline"),
    )),
    "constitution_invitation": ("Einladung zur konstituierenden Sitzung", "§ 29 LPersVG RLP", (
        ("recipients", "Gewählte Mitglieder und sonstige Teilnahmeberechtigte", "multiline"),
        ("meeting", "Termin, Ort, Beginn und Einladungskanal", "multiline"),
        ("agenda", "Wahl des Vorsitzes und weitere gesetzlich vorgesehene Wahlen", "multiline"),
        ("handover", "Übergabe der Wahlakten", "multiline"),
        ("inviter", "Wahlvorstandsvorsitz / Unterschrift", "text"),
    )),
    "constitution_minutes": ("Niederschrift konstituierende Sitzung", "§ 29 LPersVG RLP · Konstituierung", (
        ("meeting", "Ort, Datum, Beginn und Ende", "multiline"),
        ("attendance", "Anwesenheit und Beschlussfähigkeit", "multiline"),
        ("chair_election", "Wahl des Personalratsvorsitzes: Ablauf, Stimmen, Feststellung", "multiline"),
        ("further_elections", "Weitere vorgeschriebene Wahlen und Feststellungen", "multiline"),
        ("handover", "Wahlaktenübergabe und Empfangsbestätigung", "multiline"),
        ("signatures", "Niederschrift und erforderliche Unterschriften", "multiline"),
    )),
    "archive_handover": ("Übergabeprotokoll Wahlakten", "§ 24 WOLPersVG · Aktenaufbewahrung", (
        ("from_to", "Übergebender Wahlvorstand und empfangender Personalrat", "multiline"),
        ("inventory", "Aktenverzeichnis, versiegelte Unterlagen und Vollständigkeit", "multiline"),
        ("location", "Aufbewahrungsort, Zugriffsschutz und Aufbewahrungsdauer", "multiline"),
        ("handover_on", "Übergabedatum und Ort", "text"),
        ("signatures", "Unterschriften und Empfangsbestätigung", "multiline"),
    )),
    "result_notice": ("Bekanntgabe des Wahlergebnisses", "LPersVG / WOLPersVG · Wahlvorstand", (
        ("determination", "Feststellung des Wahlergebnisses / Beschluss", "multiline"),
        ("elected", "Gewählte Mitglieder und Ersatzmitglieder (rechtlich zulässig)", "multiline"),
        ("public_details", "Für die Bekanntgabe zulässige weitere Angaben", "multiline"),
        ("publication", "Bekanntgabe: Ort, Datum und Nachweis", "multiline"),
    )),
}

def clean(value: str, limit: int = 250) -> str:
    value = str(value or "").replace("\x00", "").strip()
    if len(value) > limit:
        raise HTTPException(422, f"Maximal {limit} Zeichen zulässig.")
    return value

def parse_date(value: str):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise HTTPException(422, "Bitte ein gültiges Kalenderdatum angeben.")

def scope(db, election_id: int, user: User, capability: str = "read"):
    election = db.get(PRElection, election_id)
    if not user.active:
        raise HTTPException(403, "Dieses Benutzerkonto ist nicht aktiv.")
    if election is not None and not active_path(db, election.org_id):
        raise HTTPException(403, "Die zugeordnete Organisationseinheit ist nicht mehr aktiv.")
    if election is None:
        raise HTTPException(404, "Diese Wahl existiert nicht.")
    role = db.scalar(select(PRMandate.role).where(PRMandate.election_id == election_id,
                                                  PRMandate.user_id == user.id))
    # Global platform administrators never inherit access to confidential election records.
    if not role:
        raise HTTPException(404, "Diese Wahl steht dir nicht zur Verfügung.")
    if capability == "edit" and role not in EDIT_ROLES:
        raise HTTPException(403, "Für diese Änderung ist ein Wahlvorstands- oder Einrichtungsmandat erforderlich.")
    if capability == "manage" and role not in {"coordinator", "chair"}:
        raise HTTPException(403, "Die Mitgliederverwaltung ist nur für Einrichtung und Vorsitz möglich.")
    if capability == "board" and role != "chair":
        raise HTTPException(403, "Diese Prüfung ist nur durch den zugeordneten Wahlvorstandsvorsitz möglich.")
    return election, role

def record(db, user_id: int, election_id: int, action: str, target: str = ""):
    db.add(PRAudit(actor_id=user_id, election_id=election_id, action=action, target=target))

def document_values(doc: PRDocument) -> dict[str, str]:
    try:
        decrypted = decrypt(doc.payload_enc)
        if not decrypted:
            raise HTTPException(500, "Das Dokument konnte nicht entschlüsselt werden.")
        raw = json.loads(decrypted)
    except (ValueError, TypeError):
        raise HTTPException(500, "Das Dokument kann nicht entschlüsselt werden.")
    if not isinstance(raw, dict):
        raise HTTPException(500, "Das Dokumentformat ist ungültig.")
    return {k: str(v) for k,v in raw.items() if isinstance(k,str) and isinstance(v,str)}

def secure_payload(form: dict, kind: str) -> str:
    if kind not in FORM_KINDS:
        raise HTTPException(422, "Unbekannter Vordruck.")
    valid = {field[0]: clean(form.get(field[0], ""), 3000 if field[2] == "multiline" else 350)
             for field in FORM_KINDS[kind][2]}
    return encrypt(json.dumps(valid, ensure_ascii=False))
