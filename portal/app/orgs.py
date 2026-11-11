"""Körperschaften und Einrichtungen – portalweite Stammdaten (Verwaltung › Körperschaften).

Gebietskörperschaften (Verbandsgemeinde, Ortsgemeinden, Städte, Landkreis), Zweckverbände und ihre
Einrichtungen (Abteilungen, Kitas, Schulen, Bauhof …) als Baum. Genutzt von:
- Ressourcen: Anbieter einer Ressource (Filter, Kontakt, Wappen auf der öffentlichen Seite)
- Krankmelder: Arbeitgeber (jede Körperschaft oder Einrichtung einzeln wählbar)
- Rechtstexte: Ebenen im Rechtsbaum (Wappen, Kontakt)
- Anträge: zuständige Stelle
"""

import re
import secrets
from pathlib import Path

from sqlalchemy import func, select

from .config import settings
from .db import Organization

# Art → (Bezeichnung, Symbol, Gebietskörperschaft/Verband?)
KINDS = {
    "vg": ("Verbandsgemeinde", "fa-building-columns", True),
    "og": ("Ortsgemeinde", "fa-house-flag", True),
    "stadt": ("Stadt", "fa-city", True),
    "lk": ("Landkreis", "fa-map", True),
    "zv": ("Zweckverband", "fa-handshake", True),
    "einrichtung": ("Einrichtung", "fa-building-user", False),
    "abteilung": ("Abteilung / Fachbereich", "fa-sitemap", False),
    "kita": ("Kita", "fa-children", False),
    "schule": ("Schule", "fa-school", False),
    "betrieb": ("Eigenbetrieb / Werk", "fa-industry", False),
    "arbeitgeber": ("Arbeitgeber", "fa-briefcase", False),
}
BODY_KINDS = tuple(k for k, v in KINDS.items() if v[2])
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_LOGO = 2 * 1024 * 1024


def kind_label(org: Organization | None) -> str:
    return KINDS.get(org.kind, (org.kind,))[0] if org else ""


def is_body(org: Organization) -> bool:
    return org.kind in BODY_KINDS


def label(org: Organization | None) -> str:
    return (org.short_name or org.name) if org else ""


def all_orgs(db, active_only: bool = False) -> list[Organization]:
    q = select(Organization).order_by(Organization.position, Organization.name)
    if active_only:
        q = q.where(Organization.active.is_(True))
    return list(db.scalars(q))


def tree(db, active_only: bool = False) -> list[tuple[Organization, int]]:
    """Alle Einträge in Baumreihenfolge mit Tiefe – für Listen und Auswahlfelder."""
    items = all_orgs(db, active_only)
    ids = {o.id for o in items}
    kids: dict[int | None, list[Organization]] = {}
    for o in items:
        kids.setdefault(o.parent_id if o.parent_id in ids else None, []).append(o)
    out: list[tuple[Organization, int]] = []
    seen = set()
    stack = [(o, 0) for o in reversed(kids.get(None, []))]
    while stack:
        node, depth = stack.pop()
        if node.id in seen:
            continue
        seen.add(node.id)
        out.append((node, depth))
        stack.extend((child, depth + 1) for child in reversed(kids.get(node.id, [])))
    return out


def options(
    db, bodies_only: bool = False, active_only: bool = True
) -> list[tuple[int, str]]:
    """(id, eingerückter Name) für <select>. bodies_only: nur Körperschaften/Verbände (z. B. Anbieter)."""
    return [
        (o.id, "\u2003" * depth + o.name)
        for o, depth in tree(db, active_only)
        if not bodies_only or is_body(o)
    ]


def body_of(org: Organization | None) -> Organization | None:
    """Die Körperschaft, zu der eine Einrichtung gehört (sie selbst, wenn sie eine ist)."""
    seen = set()
    while org is not None and not is_body(org) and org.parent is not None:
        if org.id in seen:
            return None
        seen.add(org.id)
        org = org.parent
    return org


def path(org: Organization | None) -> list[Organization]:
    out, seen = [], set()
    while org is not None and org.id not in seen:
        out.insert(0, org)
        seen.add(org.id)
        org = org.parent
    return out


def usage(db, org: Organization) -> dict[str, int]:
    """Wo eine Körperschaft verwendet wird (vor dem Löschen anzeigen)."""
    from .db import Form, KrankEmployer, LawLevel, Resource
    from .org_models import OrgMembership, OrgRoleGrant
    from .calendar_models import Calendar, CalendarEvent
    from .leave_models import LeaveRequest, LeavePolicy
    from .leave_extensions import Closure

    return {
        "Kalender": db.scalar(
            select(func.count(Calendar.id)).where(Calendar.org_id == org.id)
        )
        or 0,
        "Kalendertermine": db.scalar(
            select(func.count(CalendarEvent.id)).where(CalendarEvent.org_id == org.id)
        )
        or 0,
        "Urlaubsplanung": db.scalar(
            select(func.count(LeaveRequest.id)).where(LeaveRequest.org_id == org.id)
        )
        or 0,
        "Urlaubsregeln": db.scalar(
            select(func.count(LeavePolicy.org_id)).where(LeavePolicy.org_id == org.id)
        )
        or 0,
        "Schließzeiten": db.scalar(
            select(func.count(Closure.id)).where(Closure.org_id == org.id)
        )
        or 0,
        "Personenzuordnungen": db.scalar(
            select(func.count(OrgMembership.id)).where(OrgMembership.org_id == org.id)
        )
        or 0,
        "Bereichsrollen": db.scalar(
            select(func.count(OrgRoleGrant.id)).where(OrgRoleGrant.org_id == org.id)
        )
        or 0,
        "Ressourcen": db.scalar(
            select(func.count(Resource.id)).where(Resource.provider_id == org.id)
        )
        or 0,
        "Krankmelder-Arbeitgeber": db.scalar(
            select(func.count(KrankEmployer.id)).where(KrankEmployer.org_id == org.id)
        )
        or 0,
        "Rechtstext-Ebenen": db.scalar(
            select(func.count(LawLevel.id)).where(LawLevel.org_id == org.id)
        )
        or 0,
        "Formulare/Anträge": db.scalar(
            select(func.count(Form.id)).where(Form.org_id == org.id)
        )
        or 0,
        "Einrichtungen": len(org.children),
    }


def would_cycle(org: Organization, parent: Organization | None) -> bool:
    seen = set()
    while parent is not None:
        if parent.id in seen:
            return True
        seen.add(parent.id)
        if parent.id == org.id:
            return True
        parent = parent.parent
    return False


def clean(
    data, org: Organization | None = None, available_kinds=None
) -> tuple[dict, list[str]]:
    def txt(key, n):
        return " ".join(str(data.get(key, "") or "").split())[:n]

    values = {
        "name": txt("name", 200),
        "short_name": txt("short_name", 80),
        "ags": txt("ags", 20),
        "street": txt("street", 255),
        "zip": txt("zip", 10),
        "city": txt("city", 200),
        "phone": txt("phone", 60),
        "email": txt("email", 255).lower(),
        "website": txt("website", 255),
        "contact": txt("contact", 255),
        "note": str(data.get("note", "") or "").strip()[:4000],
    }
    kind = str(data.get("kind", "") or "")
    values["kind"] = kind if kind in (available_kinds or KINDS) else "einrichtung"
    color = str(data.get("color", "") or "").strip()
    values["color"] = color if COLOR_RE.match(color) else ""
    if values["website"] and not values["website"].startswith(("http://", "https://")):
        values["website"] = "https://" + values["website"]
    errors = []
    if not values["name"]:
        errors.append("Bitte einen Namen angeben.")
    if values["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", values["email"]):
        errors.append("Die E-Mail-Adresse ist ungültig.")
    return values, errors


# --- Wappen / Logo -------------------------------------------------------------------------


def logo_dir() -> Path:
    d = settings.data_dir / "orgs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sniff(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def prepare_logo(content: bytes):
    if len(content) > MAX_LOGO:
        return None, "Das Wappen ist größer als 2 MB."
    mime = sniff(content)
    if mime is None:
        return (
            None,
            "Bitte ein Bild als PNG, JPEG oder WebP hochladen. SVG wird nicht unterstützt.",
        )
    name = secrets.token_hex(8) + LOGO_TYPES[mime]
    (logo_dir() / name).write_bytes(content)
    return name, None


def discard_logo(name):
    if name and Path(name).name == name:
        (logo_dir() / name).unlink(missing_ok=True)


def store_logo(org: Organization, content: bytes) -> str | None:
    name, error = prepare_logo(content)
    if error:
        return error
    previous = org.logo
    org.logo = name
    discard_logo(previous)
    return None


def remove_logo(org: Organization) -> None:
    discard_logo(org.logo)
    org.logo = ""


def logo_url(org: Organization | None) -> str:
    return f"/org/{org.id}/logo?v={org.logo[:6]}" if org and org.logo else ""
