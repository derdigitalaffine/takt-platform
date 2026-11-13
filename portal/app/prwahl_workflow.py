"""Paper-election lifecycle and independent arithmetic checks.

No voter-level ballot or voting token. All counts are aggregate, manually
entered and require an explicit board confirmation before finalization.
"""
from collections import defaultdict
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from fastapi import HTTPException
from .db import Base, utcnow

STAGES = (
    ("appointment", "Wahlvorstand bestellen", "§ 16 LPersVG: Bestellung, Vorsitz, Vertretung und Gruppenrepräsentation dokumentieren"),
    ("preparation", "Wahl vorbereiten", "§§ 2–5 WOLPersVG: Wahlberechtigtenverzeichnis, Einsprüche, Gruppen und Sitze prüfen"),
    ("announcement", "Wahl einleiten", "§§ 1, 6 WOLPersVG: Beschluss, Unterschriften und Bekanntgabe des Wahlausschreibens nachweisen"),
    ("nominations", "Wahlvorschläge prüfen", "§§ 7–13 WOLPersVG: Einreichung, Zulassung, Nachfrist und Bekanntgabe prüfen"),
    ("ballots", "Papierwahl organisieren", "Stimmzettel, Wahllokal, schriftliche Stimmabgabe und Helfende"),
    ("counting", "Öffentlich auszählen", "§§ 20–21 WOLPersVG: Öffentliche Auszählung und Wahlniederschrift dokumentieren"),
    ("determination", "Ergebnis feststellen", "§§ 20–23 WOLPersVG: Beschluss, Benachrichtigung und Bekanntgabe prüfen"),
    ("constitution", "Konstituierende Sitzung", "Einladung, Vorsitzwahl und Übergabe der Wahlakten"),
    ("archive", "Wahlakten übergeben", "Aufbewahrung, Nachweise und Abschluss"),
)
STAGE_IDS = {x[0] for x in STAGES}

class PRMilestone(Base):
    __tablename__ = "pr_milestones"
    __table_args__ = (UniqueConstraint("election_id", "stage", name="uq_pr_milestone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    stage: Mapped[str] = mapped_column(String(28))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    evidence: Mapped[str] = mapped_column(String(500), default="")
    effective_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class PRCountRound(Base):
    __tablename__ = "pr_count_rounds"
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    group_name: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20), default="list")
    seats: Mapped[int] = mapped_column(Integer)
    eligible: Mapped[int] = mapped_column(Integer)
    voters: Mapped[int] = mapped_column(Integer)
    ballots_cast: Mapped[int] = mapped_column(Integer)
    invalid_ballots: Mapped[int] = mapped_column(Integer)
    abstentions: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    count_reference: Mapped[str] = mapped_column(String(250), default="")
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class PRCountEntry(Base):
    __tablename__ = "pr_count_entries"
    __table_args__ = (UniqueConstraint("round_id", "label", name="uq_pr_count_entry"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("pr_count_rounds.id", ondelete="RESTRICT"), index=True)
    label: Mapped[str] = mapped_column(String(180))
    votes: Mapped[int] = mapped_column(Integer)

def _integer(value, label, *, minimum=0, maximum=10000000):
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise HTTPException(422, f"{label}: Bitte eine ganze Zahl eingeben.")
    if n < minimum or n > maximum:
        raise HTTPException(422, f"{label}: Wert außerhalb des zulässigen Bereichs.")
    return n

def validate_totals(*, eligible, voters, ballots_cast, invalid_ballots, abstentions):
    eligible = _integer(eligible, "Wahlberechtigte")
    voters = _integer(voters, "Wählende")
    ballots_cast = _integer(ballots_cast, "Stimmzettel")
    invalid_ballots = _integer(invalid_ballots, "Ungültige Stimmzettel")
    abstentions = _integer(abstentions, "Ohne gültige Stimmabgabe")
    if voters > eligible or ballots_cast > voters or invalid_ballots > ballots_cast:
        raise HTTPException(422, "Die Zahlen der Wahlberechtigten, Wählenden, Stimmzettel und ungültigen Stimmzettel sind nicht plausibel.")
    if abstentions > ballots_cast - invalid_ballots:
        raise HTTPException(422, "Die Zahl ohne gültige Stimmabgabe ist zu hoch.")
    return eligible, voters, ballots_cast, invalid_ballots, abstentions

def parse_entries(raw: str):
    """One candidate/list per line, separated from votes by a tab or final semicolon."""
    if len(raw) > 20000:
        raise HTTPException(422, "Die Erfassung ist zu umfangreich.")
    entries = []
    seen = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        if "\t" in line:
            name, votes = line.rsplit("\t", 1)
        elif ";" in line:
            name, votes = line.rsplit(";", 1)
        else:
            raise HTTPException(422, "Pro Zeile Bezeichnung und Stimmen durch Semikolon oder Tab trennen.")
        name = name.strip()
        if not name or len(name) > 180 or name.casefold() in seen:
            raise HTTPException(422, "Leere, doppelte oder zu lange Listen-/Personenbezeichnung.")
        seen.add(name.casefold())
        entries.append((name, _integer(votes.strip(), f"Stimmen für {name}")))
    if not entries or len(entries) > 150:
        raise HTTPException(422, "Bitte zwischen 1 und 150 Listen oder Personen erfassen.")
    return entries

def dhondt(entries, seats):
    """Exact integer comparison; ties are flagged, NEVER resolved automatically.

    This is a calculation aid for a manually selected and reviewed list-vote
    configuration, not a legally binding allocation or a candidate ranking.
    """
    seats = _integer(seats, "Sitze", minimum=1, maximum=200)
    if not entries:
        raise HTTPException(422, "Für die Berechnung sind gültige Stimmen erforderlich.")
    # Defensive checks: callers may invoke this helper directly, bypassing
    # parse_entries. Duplicate names would overwrite the assignment map.
    names = [name for name, _ in entries]
    if any(not isinstance(name, str) or not name.strip() or len(name) > 180 for name in names):
        raise HTTPException(422, "Ungültige Listenbezeichnung.")
    if len({name.strip().casefold() for name in names}) != len(names):
        raise HTTPException(422, "Listenbezeichnungen müssen eindeutig sein.")
    if any(not isinstance(votes, int) or isinstance(votes, bool) or votes < 0 for _, votes in entries):
        raise HTTPException(422, "Stimmen müssen nichtnegative ganze Zahlen sein.")
    if sum(votes for _, votes in entries) == 0:
        raise HTTPException(422, "Für die Berechnung sind gültige Stimmen erforderlich.")
    assigned = {name: 0 for name,_ in entries}
    rows = []
    for index in range(seats):
        quotients = [(name, votes, assigned[name] + 1) for name,votes in entries]
        winner = quotients[0]
        ties = [winner]
        for contender in quotients[1:]:
            a, av, ad = contender
            _, wv, wd = winner
            comparison = av * wd - wv * ad
            if comparison > 0:
                winner, ties = contender, [contender]
            elif comparison == 0:
                ties.append(contender)
        if len(ties) != 1:
            return {"assigned": assigned, "rows": rows,
                    "tie": {"seat": index + 1, "labels": [n for n,_,_ in ties]},
                    "complete": False}
        name, votes, divisor = winner
        assigned[name] += 1
        rows.append({"seat": index+1, "label": name, "votes": votes, "divisor": divisor})
    return {"assigned": assigned, "rows": rows, "tie": None, "complete": True}

def check_count(mode, seats, ballots_cast, invalid_ballots, abstentions, entries):
    if mode not in {"list", "person"}:
        raise HTTPException(422, "Unbekanntes Zählverfahren.")
    seats = _integer(seats, "Sitze", minimum=1, maximum=200)
    valid_ballots = ballots_cast - invalid_ballots
    total = sum(v for _,v in entries)
    if mode == "list":
        if total + abstentions != valid_ballots:
            raise HTTPException(422, "Listenstimmen plus Stimmzettel ohne gültige Stimmabgabe stimmen nicht mit den gültigen Stimmzetteln überein.")
        return dhondt(entries, seats)
    # A person ballot can carry multiple candidate votes: never equate candidate
    # votes with ballots or silently apply a list-election seat formula.
    if total > valid_ballots * seats:
        raise HTTPException(422, "Es wurden mehr Personenstimmen als maximal mögliche Stimmen erfasst.")
    return {"assigned": {}, "rows": [], "tie": None, "complete": False,
            "note": "Personenwahl: Kandidatenstimmen erfasst. Mandatsfeststellung und gesetzliche Sonderregeln müssen durch den Wahlvorstand geprüft werden."}
