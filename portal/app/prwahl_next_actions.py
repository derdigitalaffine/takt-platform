"""Read-only prioritized next actions for a protected election workspace.

These indicators express missing work evidence, NEVER formal legal validity.
They contain no voter data and never trigger publication or notifications.
"""


def next_actions(election, role, mandates, documents, events, completed_stages):
    can_edit = role in {"coordinator", "chair", "member", "clerk"}
    can_manage = role in {"coordinator", "chair"}
    action = []

    def add(code, title, explanation, href, *, icon, tone="neutral"):
        action.append(dict(code=code, title=title, explanation=explanation,
                           href=href if can_edit else "", icon=icon, tone=tone))

    if election.legal_gate != "approved":
        add("legal", "Rechtsprüfung ausstehend",
            "Amtliche Muster, Wahlkörper und Fristen benötigen eine unabhängige fachliche Freigabe. Keine digitale Phasenmarkierung ersetzt diese.",
            "", icon="fa-scale-balanced", tone="caution")

    if not any(m.role == "chair" for m, _ in mandates):
        add("chair", "Vorsitz des Wahlvorstands zuordnen",
            "Eine benannte Person mit nachgewiesener Bestellung auswählen; die TAKT-Rolle ersetzt keinen Bestellungsbeschluss.",
            f"/personalratswahl/{election.id}?tab=board" if can_manage else "",
            icon="fa-users", tone="attention")

    if not election.election_day:
        add("date", "Wahltag und Dienststelle prüfen",
            "Zunächst den Wahlzeitraum festlegen; ohne Wahltag ist keine verlässliche Terminvorschau möglich.",
            f"/personalratswahl/{election.id}?tab=overview#pr-data-form",
            icon="fa-calendar-days", tone="attention")

    if not any(doc.kind == "election_notice" for doc in documents):
        add("notice_draft", "Wahlausschreiben vorbereiten",
            "Den Entwurf anhand des Landesmusters vervollständigen und durch den Wahlvorstand prüfen lassen.",
            f"/personalratswahl/{election.id}/dokumente/neu/election_notice",
            icon="fa-file-lines")

    if not events:
        add("dates", "Termine und Fristen planen",
            "Unverbindliche Terminvorschläge und die tatsächlichen Fristvoraussetzungen im Wahlkalender prüfen.",
            f"/personalratswahl/{election.id}/termine",
            icon="fa-calendar-check")

    if "announcement" not in completed_stages and election.election_day:
        add("announcement", "Bekanntmachung nachweisen",
            "Erlasstag, Aushang und echte Bekanntgabe erst nach rechtskonformer Durchführung dokumentieren.",
            f"/personalratswahl/{election.id}/ablauf",
            icon="fa-clipboard-check")

    return action[:5]
