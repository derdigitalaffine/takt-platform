"""Editable A4 Word proofs without third-party document dependencies.

Uses a minimal, standards-based OPC/WordprocessingML package. Legal wording
remains an unapproved draft; original ink signatures and prescribed channels
are never replaced by this download.
"""
from __future__ import annotations

import io
import re
from datetime import timezone
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from .prwahl import FORM_KINDS, document_values
from .db import utcnow

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _safe(value, max_chars=4000):
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or "")[:max_chars])
    return escape(text, {"'": "&apos;", '"': "&quot;"})


def _run(value, *, bold=False, color="17283B", size=22):
    spans = str(value or "").split("\n")
    body = ""
    for index, part in enumerate(spans):
        if index:
            body += "<w:br/>"
        body += f'<w:t xml:space="preserve">{_safe(part)}</w:t>'
    return (f'<w:r><w:rPr>{"<w:b/>" if bold else ""}'
            f'<w:color w:val="{color}"/><w:sz w:val="{size}"/></w:rPr>'
            + body + "</w:r>")


def _p(value, *, style="Normal", bold=False, color="17283B", size=22, after=140):
    return (f'<w:p><w:pPr><w:pStyle w:val="{style}"/>'
            f'<w:spacing w:after="{after}"/></w:pPr>'
            + _run(value, bold=bold, color=color, size=size) + "</w:p>")


def _table_row(label, value):
    return ("<w:tr>"
            '<w:tc><w:tcPr><w:tcW w:w="2450" w:type="dxa"/>'
            '<w:shd w:fill="EFF4F8"/></w:tcPr>'
            + _p(label, bold=True, color="42576B", size=18, after=40) + "</w:tc>"
            '<w:tc><w:tcPr><w:tcW w:w="6700" w:type="dxa"/>'
            '<w:shd w:fill="EFF4F8"/></w:tcPr>'
            + _p(value, size=20, after=40) + "</w:tc></w:tr>")


def _field(label, value):
    return (_p(label, bold=True, color="52697A", size=17, after=70)
            + (_p(value, size=21, after=170) if str(value or "").strip()
               else _p("Nicht ausgefüllt – vor Verwendung prüfen", color="8A6570", size=19, after=190))
            + '<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="4" '
              'w:color="D9E2EA"/></w:pBdr><w:spacing w:after="200"/></w:pPr></w:p>')


def build(election, doc) -> bytes:
    name, reference, fields = FORM_KINDS[doc.kind]
    data = document_values(doc)
    created = utcnow().replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    top = (
        _p("TAKT  /  PERSONALRATSWAHL  /  ARBEITSUNTERLAGE",
           bold=True, color="246E8D", size=16, after=120)
        + _p(name, bold=True, color="17283B", size=34, after=100)
        + _p(f"{reference}  ·  Dokumentversion {doc.revision}",
             color="586B7B", size=19, after=300)
        + '<w:tbl><w:tblPr><w:tblW w:w="9150" w:type="dxa"/>'
          '<w:tblBorders><w:insideH w:val="single" w:sz="4" w:color="DCE4EB"/></w:tblBorders>'
          '</w:tblPr>'
        + _table_row("Dienststelle", election.service_name)
        + _table_row("Wahl", election.title)
        + _table_row("Geplanter Termin", election.election_day.strftime("%d.%m.%Y")
                     if election.election_day else "Noch offen")
        + "</w:tbl>"
        + _p("PRÜFENTWURF · NICHT ZUR UNGEPRÜFTEN BEKANNTGABE",
             bold=True, color="B34253", size=19, after=330)
    )
    body = "".join(_field(label, data.get(key, "")) for key, label, _ in fields)
    end = (
        _p("PRÜFVERMERK UND UNTERSCHRIFTEN", bold=True,
           color="246E8D", size=19, after=170)
        + _p("Fachliche Kontrolle, vorgeschriebene Originalunterschriften, "
             "Aushang, Fristen und Form müssen unabhängig von diesem "
             "bearbeitbaren Entwurf nachgewiesen werden.",
             color="586B7B", size=18, after=280)
        + _p("___________________________________________________________",
             color="586B7B", size=19, after=70)
        + _p("Ort, Datum, eigenhändige Unterschrift(en) des zuständigen Wahlvorstands",
             color="586B7B", size=17, after=250)
        + _p(f"Vertraulich · Prüfentwurf · Fassung {doc.revision}",
             color="586B7B", size=16, after=0)
    )
    document_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<w:document xmlns:w="{W}"><w:body>'
                    + top + body + end
                    + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                      '<w:pgMar w:top="1380" w:right="1080" w:bottom="1380" '
                      'w:left="1080" w:header="500" w:footer="500"/>'
                      '</w:sectPr></w:body></w:document>')
    styles_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  f'<w:styles xmlns:w="{W}">'
                  '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
                  '<w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Aptos" '
                  'w:hAnsi="Aptos"/><w:sz w:val="21"/></w:rPr></w:style>'
                  '</w:styles>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            'Target="docProps/core.xml"/>'
            '</Relationships>')
    word_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                 'Target="styles.xml"/></Relationships>')
    content_types = ('<?xml version="1.0" encoding="UTF-8"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '<Override PartName="/word/styles.xml" '
                     'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                     '<Override PartName="/docProps/core.xml" '
                     'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                     '</Types>')
    core_xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                'xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f'<dc:title>{_safe(name)}</dc:title>'
                '<dc:creator>TAKT Personalratswahl</dc:creator>'
                f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
                '</cp:coreProperties>')
    result = io.BytesIO()
    with ZipFile(result, "w", compression=ZIP_DEFLATED) as docx:
        for name, value in (
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", rels),
            ("word/document.xml", document_xml),
            ("word/styles.xml", styles_xml),
            ("word/_rels/document.xml.rels", word_rels),
            ("docProps/core.xml", core_xml),
        ):
            docx.writestr(name, value.encode("utf-8"))
    return result.getvalue()
