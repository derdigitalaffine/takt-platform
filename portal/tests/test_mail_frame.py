"""E-Mails im Erscheinungsbild der Organisation (HTML-Rahmen mit Farbe, Logo, Fußzeile)."""

import io

from PIL import Image

from app import branding, notify

from conftest import login

ADMIN = ("admin@example.org", "admin-passwort-123")
CFG = {"mail_from": "portal@example.org", "smtp_host": "smtp.example.org"}


def _logo() -> str:
    branding.BRAND_DIR.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    Image.new("RGB", (120, 40), (10, 80, 160)).save(buf, "PNG")
    (branding.BRAND_DIR / "logo-test.png").write_bytes(buf.getvalue())
    return "logo-test.png"


def test_framed_mail_with_inline_logo():
    cfg = {**CFG, "ui_custom": "1", "ui_primary": "#16a34a", "ui_logo": _logo(), "ui_brand_name": "VG Musterdorf",
           "ui_footer_text": "Verbandsgemeinde Musterdorf, Rathausplatz 1", "ui_imprint_url": "/impressum"}
    msg = notify._build(cfg, "a@example.org", "Betreff", "Hallo,\n\nsiehe https://portal.example.org/x\n\nGruß")
    html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    html = html_part.get_content()
    assert "background:#16a34a" in html and "VG Musterdorf" in html and 'src="cid:logo@portal"' in html
    assert "Rathausplatz 1" in html and "https://portal.example.org/impressum" in html
    assert any(p.get_content_type() == "image/png" and p["Content-ID"] == "<logo@portal>" for p in msg.walk())
    plain = next(p for p in msg.walk() if p.get_content_type() == "text/plain").get_content()
    assert plain.startswith("Hallo,") and "<" not in plain


def test_plain_when_switched_off_and_preview():
    msg = notify._build({**CFG, "ui_mail_frame": "0"}, "a@example.org", "x", "Text")
    html = next(p for p in msg.walk() if p.get_content_type() == "text/html").get_content()
    assert "<table" not in html and "<p" in html
    c = login(*ADMIN)
    r = c.get("/admin/design/mail-vorschau")
    assert r.status_code == 200 and "<table" in r.text and "img-src data:" in r.headers["content-security-policy"]


def test_guest_booking_html_remains_mail_body_with_ics_invitation():
    """Real iMIP shape: branded HTML is the mail body, not overridden by calendar."""
    calendar = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nMETHOD:REQUEST\r\nEND:VCALENDAR\r\n"
    text = (
        "Guten Tag Erika,\n\nIhr Termin ist verbindlich bestätigt.\n\n"
        "TERMINÜBERSICHT\nAnliegen: Bauberatung\nDatum: 18.11.2026\n"
        "Uhrzeit: 10:00–10:45 Uhr\nOrt: Rathaus\n\n"
        "Termin ansehen, verschieben oder absagen:\n"
        "https://portal.example.org/b/m/beispiel"
    )
    cfg = {**CFG, "ui_mail_frame": "1", "ui_custom": "1",
           "ui_primary": "#184d83", "ui_brand_name": "VG Musterdorf"}
    mail = notify._build(
        cfg, "gast@example.org", "Ihr Termin ist bestätigt", text,
        [{"filename": "termin.ics", "content": calendar, "calendar_method": "REQUEST"}],
        kind="booking_confirm",
    )
    assert mail.get_content_type() == "multipart/mixed"
    parts = list(mail.iter_parts())
    assert [p.get_content_type() for p in parts] == [
        "multipart/alternative", "text/calendar", "application/ics",
    ]
    alternatives = list(parts[0].iter_parts())
    assert alternatives[0].get_content_type() == "text/plain"
    assert alternatives[-1].get_content_type() in {"text/html", "multipart/related"}
    html = next(p for p in mail.walk() if p.get_content_type() == "text/html").get_content()
    assert "Ihr Termin" in html and "Bauberatung" in html
    assert "background:#184d83" in html
    assert 'href="https://portal.example.org/b/m/beispiel"' in html
    assert "TERMINÜBERSICHT" in next(
        p for p in mail.walk() if p.get_content_type() == "text/plain"
    ).get_content()
    assert parts[1].get_param("method") == "REQUEST"
    assert parts[1].get_payload(decode=True).decode("utf-8") == calendar
    assert parts[2].get_filename() == "termin.ics"


def test_legacy_custom_booking_template_has_styled_summary_and_safe_text():
    """Administrators need not reset existing overrides to receive good HTML."""
    body = (
        "Guten Tag,\n\nIhr Termin steht fest.\n\n"
        "Termin: 18.11.2026, 10:00 Uhr\n"
        "Ort: Rathaus <b>Altstadt</b>\n\n"
        "Termin verwalten:\nhttps://portal.example.org/b/m/alt"
    )
    mail = notify._build(
        {**CFG, "ui_mail_frame": "1"},
        "a@example.org", "Termin", body, kind="booking_confirm",
    )
    html = next(p for p in mail.walk() if p.get_content_type() == "text/html").get_content()
    assert "Termin bestätigt" in html and "Ihr Termin" in html
    assert "18.11.2026" in html
    assert "&lt;b&gt;Altstadt&lt;/b&gt;" in html
    assert 'href="https://portal.example.org/b/m/alt"' in html
