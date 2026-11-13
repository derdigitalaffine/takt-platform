"""Election-only scheduling: no confidential details in external calendar feeds."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utcnow

TZ = ZoneInfo("Europe/Berlin")
KINDS = {
 "board": "Sitzung des Wahlvorstands",
 "roll": "Prüfung Wahlberechtigtenverzeichnis",
 "notice": "Bekanntgabe Wahlausschreiben",
 "nomination": "Ende Einreichung Wahlvorschläge",
 "ballot": "Papierwahl",
 "count": "Öffentliche Auszählung",
 "result": "Bekanntgabe Wahlergebnis",
 "constitution": "Konstituierende Sitzung",
 "other": "Weiterer Wahltermin",
}

class PRScheduleEvent(Base):
    __tablename__ = "pr_schedule_events"
    __table_args__ = (UniqueConstraint("election_id", "uid", name="uq_pr_event_uid"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("pr_elections.id", ondelete="RESTRICT"), index=True)
    uid: Mapped[str] = mapped_column(String(90))
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(180))
    location: Mapped[str] = mapped_column(String(240), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    audience: Mapped[str] = mapped_column(String(16), default="board")
    status: Mapped[str] = mapped_column(String(16), default="planned")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

def local_to_utc(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            raise ValueError()
        # Round-trip validation avoids silently shifting missing DST wall times.
        aware = dt.replace(tzinfo=TZ)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(TZ).replace(tzinfo=None) != dt:
            raise ValueError()
        return utc.replace(tzinfo=None)
    except (TypeError, ValueError):
        raise HTTPException(422, "Ungültige Ortszeit (Europe/Berlin), bitte Sommerzeitwechsel beachten.")

def display_local(value):
    return value.replace(tzinfo=timezone.utc).astimezone(TZ).strftime("%d.%m.%Y %H:%M")

def ics_escape(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;").replace("\r", "")

def calendar_file(event):
    def stamp(dt):
        return dt.replace(tzinfo=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fields = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//TAKT//Personalratswahl//DE",
              "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
              "UID:"+event.uid, "DTSTAMP:"+stamp(event.updated_at or event.created_at),
              "DTSTART:"+stamp(event.starts_at), "DTEND:"+stamp(event.ends_at),
              "SEQUENCE:"+str(event.sequence), "SUMMARY:"+ics_escape(event.title),
              "LOCATION:"+ics_escape(event.location),
              "STATUS:"+("CANCELLED" if event.status=="cancelled" else "CONFIRMED"),
              "END:VEVENT", "END:VCALENDAR"]
    # RFC 5545: CRLF and UTF-8 folding at <=75 octets per content line.
    folded = []
    for field in fields:
        line = ""
        for ch in field:
            if len((line+ch).encode("utf-8")) > 75:
                folded.append(line)
                line = " " + ch
            else:
                line += ch
        folded.append(line)
    return "\r\n".join(folded)+"\r\n"
