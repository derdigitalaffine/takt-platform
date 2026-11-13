"""Branded, confidential A4 proof copies for RLP paper-election administration.

A generated proof is NEVER a legal ruleset approval, signature or publication.
It is deliberately watermarked until independent legal review is implemented.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import branding
from .db import get_settings, to_local, utcnow
from .prwahl import FORM_KINDS, document_values

INK = "#17283B"
MUTED = "#586B7B"
EDGE = "#DCE4EB"
ACCENT = "#246E8D"

def _font():
    if "ElectionSans" in pdfmetrics.getRegisteredFontNames():
        return "ElectionSans"
    import reportlab
    path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
    if path.is_file():
        pdfmetrics.registerFont(TTFont("ElectionSans", str(path)))
        return "ElectionSans"
    return "Helvetica"

def _clean(value, size=3200):
    txt = str(value or "")[:size]
    txt = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", txt)
    return xml_escape(txt).replace("\n", "<br/>")

def build(db, election, doc) -> bytes:
    name, statute, fields = FORM_KINDS[doc.kind]
    values = document_values(doc)
    font = _font()
    settings = get_settings(db)
    brand = branding.build(settings)
    primary = brand.get("primary") or ACCENT
    if not re.fullmatch("#[0-9a-fA-F]{6}", primary):
        primary = ACCENT
    org = brand.get("name") or "TAKT"
    created = to_local(utcnow()).strftime("%d.%m.%Y · %H:%M")
    buf = io.BytesIO()
    document = SimpleDocTemplate(
        buf, pagesize=A4, rightMargin=19*mm, leftMargin=19*mm,
        topMargin=28*mm, bottomMargin=22*mm,
        title=f"Prüfentwurf – {name}", author=str(org)[:100],
        subject="Ungeprüfter Vordruck zur Personalratswahl – keine digitale Stimmabgabe",
        pageCompression=1,
    )
    styles = {
        "eyebrow": ParagraphStyle("pe", fontName=font, fontSize=8, leading=12, textColor=colors.HexColor(primary), spaceAfter=6),
        "title": ParagraphStyle("pt", fontName=font, fontSize=18, leading=22, textColor=colors.HexColor(INK), spaceAfter=8),
        "subtitle": ParagraphStyle("ps", fontName=font, fontSize=9, leading=13, textColor=colors.HexColor(MUTED), spaceAfter=13),
        "label": ParagraphStyle("pl", fontName=font, fontSize=8.2, leading=11, textColor=colors.HexColor(MUTED), spaceAfter=3),
        "text": ParagraphStyle("px", fontName=font, fontSize=10, leading=15, textColor=colors.HexColor(INK), spaceAfter=5),
        "meta": ParagraphStyle("pm", fontName=font, fontSize=8.5, leading=13, textColor=colors.HexColor(INK)),
        "note": ParagraphStyle("pn", fontName=font, fontSize=8.2, leading=12, textColor=colors.HexColor(MUTED)),
    }
    story = [
        Paragraph("PERSONALRATSWAHL  /  ARBEITSUNTERLAGE", styles["eyebrow"]),
        Paragraph(_clean(name), styles["title"]),
        Paragraph(_clean(statute) + " · Dokumentversion " + str(doc.revision), styles["subtitle"]),
    ]
    meta = [
        ["Dienststelle", Paragraph(_clean(election.service_name), styles["meta"])],
        ["Wahl / Wahlkörper", Paragraph(_clean(election.title + " · " + election.body_type), styles["meta"])],
        ["Geplanter Wahltermin", Paragraph(election.election_day.strftime("%d.%m.%Y") if election.election_day else "Noch offen", styles["meta"])],
    ]
    t = Table([[Paragraph(k, styles["label"]), v] for k,v in meta],
              colWidths=[41*mm, 129*mm], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"), ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F0F5F8")),
                           ("BOTTOMPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),9),
                           ("LEFTPADDING",(0,0),(-1,-1),10),
                           ("LINEBELOW",(0,0),(-1,-2),0.5,colors.HexColor(EDGE))]))
    story.extend([t, Spacer(1,9*mm)])
    for field, label, field_type in fields:
        raw = values.get(field, "").strip()
        value = Paragraph(_clean(raw) if raw else "<font color='#75879B'>Nicht ausgefüllt – vor Verwendung prüfen</font>", styles["text"])
        story.append(KeepTogether([
            Paragraph(_clean(label), styles["label"]),
            value,
            HRFlowable(width="100%", thickness=0.5, color=colors.HexColor(EDGE), spaceAfter=5*mm),
        ]))
    story.extend([
        Spacer(1,5*mm),
        Paragraph("PRÜFVERMERK UND UNTERSCHRIFTEN", styles["eyebrow"]),
        Paragraph("Fachliche Kontrolle, gesetzlich erforderliche Originalunterschriften, Aushang, Fristen und Form sind außerhalb dieses Programms nachzuweisen.", styles["note"]),
        Spacer(1,13*mm), HRFlowable(width="100%", thickness=0.6, color=colors.HexColor(MUTED), spaceAfter=2*mm),
        Paragraph("Ort, Datum, eigenhändige Unterschrift(en) des zuständigen Wahlvorstands", styles["note"]),
    ])
    def page(canvas, pdf):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(colors.HexColor(primary))
        canvas.rect(0,h-4*mm,w,4*mm,stroke=0,fill=1)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.setFont(font,8)
        canvas.drawString(19*mm,h-15*mm,str(org)[:62])
        canvas.drawRightString(w-19*mm,h-15*mm,"WAHLORGANISATION · RLP")
        canvas.setStrokeColor(colors.HexColor(EDGE))
        canvas.line(19*mm,17*mm,w-19*mm,17*mm)
        canvas.setFont(font,7.5)
        canvas.drawString(19*mm,12*mm,"Vertraulich · Version "+str(doc.revision)+" · "+created)
        canvas.drawRightString(w-19*mm,12*mm,f"Seite {pdf.page}")
        canvas.setFillColor(colors.Color(.62,.15,.18,alpha=.18))
        canvas.setFont(font,10.5)
        canvas.saveState()
        canvas.translate(w/2,11*mm)
        canvas.drawCentredString(0,0,"PRÜFENTWURF · NICHT ZUR UNGEPRÜFTEN BEKANNTGABE")
        canvas.restoreState()
        canvas.restoreState()
    document.build(story,onFirstPage=page,onLaterPages=page)
    return buf.getvalue()
