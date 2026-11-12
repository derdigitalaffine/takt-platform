"""Branded, privacy-first DIN A4 result reports for TAKT surveys.

This module receives only authorised survey objects from the route layer.
It renders aggregate values; no names, addresses, response IDs, edit tokens
or raw free-text answers appear in the default report.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                               Spacer, Table, TableStyle)

from . import branding, forms as fm, polls as pl
from .db import get_settings, to_local, utcnow

BLUE = "#286C92"
GREEN = "#198754"
YELLOW = "#FFC107"
RED = "#DC3545"
GREY = "#E4EAF0"
DARK = "#25364A"
MUTED = "#5A6A7B"


def _font() -> str:
    """Use bundled Unicode TrueType when available, without requiring an OS font."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "SurveySans" in pdfmetrics.getRegisteredFontNames():
        return "SurveySans"
    try:
        import reportlab
        path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        if path.is_file():
            pdfmetrics.registerFont(TTFont("SurveySans", str(path)))
            return "SurveySans"
    except (OSError, ValueError):
        pass
    return "Helvetica"


def _plain(value, max_length=1000):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return escape(value[:max_length])


def _style(font: str, *, size=10, leading=None, color=DARK, bold=False, gap=0):
    return ParagraphStyle(
        name="s%d_%d_%s_%s" % (size, gap, str(color).replace("#", ""), "b" if bold else "r"),
        fontName=font, fontSize=size, leading=leading or size * 1.42,
        textColor=colors.HexColor(color), spaceAfter=gap,
        allowWidows=0, allowOrphans=0, splitLongWords=True,
    )


def _bar(parts, width=73 * mm, height=9 * mm):
    """Vector bar: identical green/amber/red semantics to the Web UI."""
    graph = Drawing(width, height)
    graph.add(Rect(0, 0, width, height, fillColor=colors.HexColor(GREY), strokeColor=None))
    total = sum(max(0, float(value)) for value, _ in parts)
    position = 0.0
    if total:
        for value, color in parts:
            span = width * max(0, float(value)) / total
            if span:
                graph.add(Rect(position, 0, span, height,
                               fillColor=colors.HexColor(color), strokeColor=None))
                position += span
    return graph


def _report(db, title, report_type, description, metadata, story_builder):
    """Compact A4 report with a restrained header and two-column facts.

    One page is the target for ordinary polls, never a hard cap on data.
    No truncation of CSV-equivalent answer/participant details is permitted.
    """
    font = _font()
    brand = branding.build(get_settings(db))
    primary = brand.get("primary", BLUE)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", primary):
        primary = BLUE
    org_name = str(brand.get("name") or "TAKT")[:90]
    now = to_local(utcnow()).strftime("%d.%m.%Y, %H:%M Uhr")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=25 * mm, bottomMargin=17 * mm,
        title=f"{report_type} – {title}", author=org_name,
        subject="Vertraulicher kompakter Ergebnisbericht mit vollständiger CSV-Detailauswertung",
        pageCompression=1,
    )
    normal = _style(font, size=8, leading=10.5, gap=1.2 * mm)
    small = _style(font, size=7.1, leading=9, color=MUTED)
    heading = _style(font, size=14, leading=17, color=DARK, gap=2 * mm)
    section = _style(font, size=9.5, leading=12, color=DARK, gap=1 * mm)
    styles = dict(normal=normal, small=small, heading=heading, section=section,
                  label=_style(font, size=6.7, leading=9, color=MUTED),
                  count=_style(font, size=7.2, leading=9, color=DARK))

    def page(canvas, pdf):
        canvas.saveState()
        w, h = A4
        canvas.setFillColor(colors.HexColor(primary))
        canvas.rect(0, h - 3.5 * mm, w, 3.5 * mm, fill=1, stroke=0)
        canvas.setFont(font, 7.6)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(17 * mm, h - 10.5 * mm, org_name)
        canvas.drawRightString(w - 17 * mm, h - 10.5 * mm, "TAKT · ERGEBNISBERICHT")
        name = get_settings(db).get("ui_logo", "") if brand.get("custom") else ""
        if name and Path(name).name == name and name.lower().endswith((".png", ".jpg", ".jpeg")):
            path = branding.BRAND_DIR / name
            if path.is_file():
                try:
                    from reportlab.lib.utils import ImageReader
                    img = ImageReader(str(path))
                    iw, ih = img.getSize()
                    scale = min(22 * mm / iw, 6 * mm / ih)
                    canvas.drawImage(img, w - 17 * mm - iw * scale, h - 18.5 * mm,
                                     iw * scale, ih * scale, mask="auto")
                except (OSError, ValueError):
                    pass
        canvas.setStrokeColor(colors.HexColor(GREY))
        canvas.line(17 * mm, h - 21 * mm, w - 17 * mm, h - 21 * mm)
        canvas.line(17 * mm, 13 * mm, w - 17 * mm, 13 * mm)
        canvas.setFont(font, 6.8)
        canvas.drawString(17 * mm, 9 * mm, "Erstellt " + now + " · Vertraulich – nur für Berechtigte")
        canvas.drawRightString(w - 17 * mm, 9 * mm, f"Seite {pdf.page}")
        canvas.restoreState()

    items = [
        Paragraph(_plain(report_type, 100).upper(), _style(font, size=7, color=primary, gap=1.2 * mm)),
        Paragraph(_plain(title, 250), heading),
    ]
    if description:
        brief = re.sub(r"\s+", " ", str(description)).strip()
        if len(brief) > 220:
            brief = brief[:217].rstrip() + "…"
        items.append(Paragraph(_plain(brief, 240), small))
        items.append(Spacer(1, 1.2 * mm))
    facts = [(Paragraph(_plain(k, 110), styles["label"]),
              Paragraph(_plain(v, 320), styles["count"]))
             for k, v in metadata if v not in (None, "")]
    if facts:
        rows = []
        for i in range(0, len(facts), 2):
            left = facts[i]
            right = facts[i + 1] if i + 1 < len(facts) else ("", "")
            rows.append([left[0], left[1], right[0], right[1]])
        table = Table(rows, colWidths=[29 * mm, 58 * mm, 29 * mm, 58 * mm],
                      hAlign="LEFT", splitByRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#D9E3EB")),
        ]))
        items.extend([table, Spacer(1, 3 * mm)])
    items.extend(story_builder(styles, font))
    if len(items) < 3:
        items.append(Paragraph("Noch keine auswertbaren Antworten vorhanden.", normal))
    doc.build(items, onFirstPage=page, onLaterPages=page)
    return buf.getvalue()



def _chart_table(labels, values, font, *, bar_color=BLUE):
    maximum = max([int(v) for v in values] + [1])
    rows = []
    for label, value in zip(labels, values):
        span = _bar([(value, bar_color), (max(0, maximum - value), GREY)], width=72 * mm, height=4.2 * mm)
        rows.append([Paragraph(_plain(label, 110), _style(font, size=7.2, leading=9)),
                     span,
                     Paragraph(str(int(value)), _style(font, size=7.2))])
    if not rows:
        return None
    table = Table(rows, colWidths=[75 * mm, 72 * mm, 18 * mm], hAlign="LEFT", splitByRow=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, -2), .4, colors.HexColor(GREY)),
    ]))
    return table



def _csv_detail(csv_source: str, font: str, *, form: bool) -> list:
    """Show *every* CSV field without a forced page break or bulky appendix.

    Use a color-coded participant/result matrix for date polls; form questions
    receive compact, labelled table rows. Truly long open text remains
    splittable between pages: never truncate or clip it to meet a page quota.
    """
    records = list(csv.reader(io.StringIO(csv_source.lstrip("\ufeff")), delimiter=";"))
    if not records:
        return []
    headings, *rows = records
    return (_form_detail_table(headings, rows, font) if form
            else _poll_detail_grid(headings, rows, font))


def _detail_cell(value, font, *, size=7.2, color=DARK):
    return Paragraph(escape(str(value if value not in (None, "") else "–"))
                     .replace("\n", "<br/>"),
                     _style(font, size=size, leading=size * 1.32, color=color))


def _form_detail_table(headings, rows, font):
    """One compact field/value table per response; long CSV cells can split.

    A ReportLab table cannot split an oversized *single row*. For lengthy open
    text or GeoJSON we flush the short rows and render the original text as
    normal, splittable paragraphs, then continue the same response.
    """
    if not rows:
        return []
    items = [Paragraph("Einzelantworten & Teilnehmer", _style(font, size=9.5, leading=12)),
             Paragraph("Vollständige vertrauliche Angaben aus dem CSV-Export",
                       _style(font, size=7, color=MUTED, gap=2 * mm))]
    name_style = _style(font, size=8.2, leading=10.5, color=DARK, gap=0.7 * mm)
    label_style = _style(font, size=6.6, leading=8.5, color=MUTED)
    value_style = _style(font, size=7, leading=9.2, color=DARK)
    long_style = _style(font, size=7.1, leading=9.5, color=DARK)
    for index, record in enumerate(rows, 1):
        name = record[2] if len(record) > 2 else ""
        items.append(Paragraph(f"{index}. " + escape(name or "Antwort"),
                               name_style))
        short_rows = []

        def flush():
            if not short_rows:
                return
            table = Table(short_rows[:], colWidths=[42 * mm, 132 * mm],
                          hAlign="LEFT", splitByRow=1)
            table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1),
                 [colors.HexColor("#F3F7FA"), colors.white]),
                ("LINEBELOW", (0, 0), (-1, -2), .25,
                 colors.HexColor("#DDE7EE")),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ]))
            items.append(table)
            short_rows.clear()

        for column, label in enumerate(headings):
            raw = record[column] if column < len(record) else ""
            label_text = str(label or f"Spalte {column + 1}")
            if len(raw) > 650:
                flush()
                items.append(Paragraph("<b>" + escape(label_text) + ":</b>",
                                       _style(font, size=7.1, leading=9.2,
                                              color=MUTED)))
                # A true paragraph may split across pages, even for long or
                # unbroken free texts/serialized geographic coordinates.
                for pos in range(0, len(raw), 1100):
                    chunk = raw[pos:pos + 1100].replace("\r\n", "\n").replace("\r", "\n")
                    items.append(Paragraph(escape(chunk).replace("\n", "<br/>"),
                                           long_style))
            else:
                short_rows.append([
                    Paragraph(escape(label_text), label_style),
                    Paragraph(escape(raw or "–").replace("\n", "<br/>"),
                              value_style),
                ])
        flush()
        items.append(Spacer(1, 2 * mm))
    return items


def _poll_detail_grid(headings, rows, font):
    """Compact colored equivalent of the Web participant x term grid.

    Full CSV option titles are printed in the preceding term ranking, with
    matching 1-based column numbers. This grid includes each participant's
    name, email, submission time, vote and comment; summary CSV rows too.
    """
    options = headings[3:-1]
    participants = [row for row in rows if row and not row[0].startswith("Summe ")]
    totals = [row for row in rows if row and row[0].startswith("Summe ")]
    items = [
        Paragraph("Teilnehmer & Ergebnisraster", _style(font, size=9.5, leading=12)),
        Paragraph("Name · E-Mail · Geantwortet · Kommentar. "
                  "Spaltennummern entsprechen den Terminen oben.",
                  _style(font, size=7, color=MUTED, gap=1.5 * mm)),
    ]
    if not options:
        # A CSV can have no proposed dates: still show its participant details.
        items.extend(_form_detail_table(headings, participants + totals, font))
        return items
    for offset in range(0, len(options), 5):
        batch = options[offset:offset + 5]
        width = min(111 * mm, len(batch) * 24 * mm)
        first = 174 * mm - width
        widths = [first] + [width / len(batch)] * len(batch)
        header = [_detail_cell("Name / E-Mail / Geantwortet", font, size=7.1)]
        header += [_detail_cell(str(offset + i + 1), font, size=7.5)
                   for i in range(len(batch))]
        table_rows = [header]
        marks = []
        for row in participants:
            profile = "<b>" + escape(row[0] if len(row) > 0 else "") + "</b>"
            profile += "<br/>" + escape(row[1] if len(row) > 1 else "")
            profile += "<br/>" + escape(row[2] if len(row) > 2 else "")
            cells = [Paragraph(profile, _style(font, size=6.7, leading=8.3))]
            for local_index in range(len(batch)):
                idx = 3 + offset + local_index
                answer = row[idx] if idx < len(row) else ""
                color = {"Ja": "#DEF1E6", "Wenn nötig": "#FFF1BE",
                         "Nein": "#FCE4E7"}.get(answer, "#F1F4F7")
                cells.append(_detail_cell(answer, font, size=7.1))
                marks.append((len(table_rows), local_index + 1, color))
            table_rows.append(cells)
        for row in totals:
            cells = [_detail_cell(row[0], font, size=7)]
            cells += [_detail_cell(row[3 + offset + i]
                     if 3 + offset + i < len(row) else "", font, size=7)
                      for i in range(len(batch))]
            table_rows.append(cells)
        table = Table(table_rows, colWidths=widths, hAlign="LEFT", repeatRows=1,
                      splitByRow=1)
        rules = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1F7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#DBE4EC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if totals:
            rules.append(("BACKGROUND", (0, len(table_rows) - len(totals)),
                          (-1, -1), colors.HexColor("#EDF3F7")))
        for row_index, col_index, shade in marks:
            rules.append(("BACKGROUND", (col_index, row_index),
                          (col_index, row_index), colors.HexColor(shade)))
        table.setStyle(TableStyle(rules))
        items.append(table)
        if offset + len(batch) < len(options):
            items.append(Spacer(1, 1.2 * mm))
    comments = [(row[0], row[-1]) for row in participants if row and row[-1]]
    if comments:
        items.append(Spacer(1, 2 * mm))
        items.append(Paragraph("Kommentare", _style(font, size=8.5, leading=11,
                                                    color=DARK, gap=1 * mm)))
        comment_style = _style(font, size=7.1, leading=9.5)
        for person, value in comments:
            raw = escape(value).replace("\r\n", "\n").replace("\r", "\n")
            items.append(Paragraph("<b>" + escape(person) + ":</b>", comment_style))
            for pos in range(0, len(raw), 1100):
                items.append(Paragraph(raw[pos:pos + 1100].replace("\n", "<br/>"),
                                       comment_style))
    return items



def form_report(db, form) -> bytes:
    """Aggregated web summary followed by the complete CSV-equivalent detail appendix."""
    responses = list(form.responses)
    summary = fm.summary(form, responses)
    invites = list(form.invites)
    completed = sum(bool(i.submitted_at) for i in invites)
    metadata = [
        ("Umfrageart", "Formularumfrage"),
        ("Erfasst", str(len(responses)) + " Antworten"),
        ("Persönliche Einladungen", str(len(invites)) if invites else "Keine"),
        ("Einladungen beantwortet", str(completed) if invites else None),
        ("Erhebung bis", to_local(form.expires_at).strftime("%d.%m.%Y, %H:%M Uhr")
         if form.expires_at else "Ohne Enddatum"),
        ("Status", "Offen" if fm.is_open(form) else "Abgeschlossen"),
    ]
    def story(styles, font):
        items = []
        for index, result in enumerate(summary, 1):
            question = result["q"]
            title = question.get("title") or fm.TYPES[question["type"]][0]
            items.append(Paragraph(f"{index}. {_plain(title, 260)}", styles["section"]))
            items.append(Paragraph(
                f"{result['count']} von {result['total']} Antworten · {fm.TYPES[question['type']][0]}",
                styles["small"]))
            chart = result.get("chart")
            if chart:
                chart_table = _chart_table(chart.get("labels", []), chart.get("values", []), font)
                if chart_table is not None:
                    items.append(chart_table)
            elif result.get("average") is not None:
                items.append(Paragraph("Durchschnitt: " +
                                       ("%.2f" % result["average"]).replace(".", ","),
                                       styles["normal"]))
            elif result.get("points") is not None:
                items.append(Paragraph(
                    "Geografische Einzelangaben sind nur in der berechtigten Webansicht verfügbar.",
                    styles["small"]))
            else:
                items.append(Paragraph(
                    "Freitext- und Einzelantworten sind aus Datenschutzgründen nicht in diesem Bericht enthalten.",
                    styles["small"]))
            if result.get("average") is not None and chart:
                items.append(Paragraph("Durchschnitt: " +
                                       ("%.2f" % result["average"]).replace(".", ","),
                                       styles["small"]))
            items.append(Spacer(1, 5 * mm))
        items.extend(_csv_detail(fm.to_csv(form, responses), font, form=True))
        return items or [Paragraph("Noch keine Antworten.", styles["normal"])]
    return _report(db, form.title, "Ergebnisse der Formularumfrage",
                   form.description, metadata, story)


def poll_report(db, poll) -> bytes:
    answered = [p for p in poll.participants if p.answered_at]
    invited = [p for p in poll.participants if p.invited_at]
    completed_invites = [p for p in invited if p.answered_at]
    counts = pl.tally(poll)
    final_label = pl.option_parts(poll.final_option)["label"] if poll.final_option else ""
    metadata = [
        ("Umfrageart", "Terminumfrage"),
        ("Abgestimmt", str(len(answered)) + " Personen"),
        ("Eingeladen", str(len(invited)) + " Personen" if invited else "Öffentlicher Zugang"),
        ("Rücklauf Einladungen", str(len(completed_invites)) + " von " + str(len(invited))
         if invited else None),
        ("Veranstaltungsort", poll.location),
        ("Dauer", f"{poll.duration_minutes} Minuten"),
        ("Frist", to_local(poll.expires_at).strftime("%d.%m.%Y, %H:%M Uhr")
         if poll.expires_at else None),
        ("Festgelegter Termin", final_label or "Noch nicht festgelegt"),
    ]
    def story(styles, font):
        items = [Paragraph("Terminpräferenzen", styles["section"]),
                 Paragraph("Grün = Ja · Gelb = Wenn nötig · Rot = Nein. "
                           "Die Balken spiegeln die Webauswertung wider.", styles["small"]),
                 Spacer(1, 3 * mm)]
        rows = []
        for option in sorted(
                poll.options,
                key=lambda o: (counts[o.id]["yes"], counts[o.id]["maybe"], -o.id),
                reverse=True):
            count = counts[option.id]
            label = pl.option_parts(option)["label"]
            if option.note:
                label += " · " + str(option.note)[:120]
            if option.id == poll.final_option_id:
                label += " (festgelegt)"
            rows.append([
                Paragraph(_plain(label, 230), _style(font, size=8.4, leading=12)),
                _bar([(count["yes"], GREEN), (count["maybe"], YELLOW),
                      (count["no"], RED)], width=72 * mm),
                Paragraph(f'{count["yes"]} / {count["maybe"]} / {count["no"]}',
                          _style(font, size=8.1)),
            ])
        if rows:
            table = Table(rows, colWidths=[75 * mm, 72 * mm, 18 * mm], hAlign="LEFT", splitByRow=1)
            table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -2), .4, colors.HexColor(GREY)),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            items.append(table)
        else:
            items.append(Paragraph("Noch keine Terminvorschläge.", styles["normal"]))
        items += [Spacer(1, 7 * mm), Paragraph(
            "Vertraulicher Bericht mit personenbezogenen Detailangaben: "
            "nur für entsprechend berechtigte Auswertende.", styles["small"])]
        items.extend(_csv_detail(pl.to_csv(poll), font, form=False))
        return items
    return _report(db, poll.title, "Ergebnisse der Terminumfrage",
                   poll.description, metadata, story)
