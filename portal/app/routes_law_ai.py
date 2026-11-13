"""Safe Ortsrecht intake: immutable originals, human-reviewed unpublished drafts.

This deliberately has NO LLM execution, OCR, external fetch, or publication path.
Untrusted binary PDFs/DOCX/images are staged for the future isolated worker.
"""
import hashlib
import os
import re
import secrets
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import laws as lx
from .config import settings
from .db import LawText, User, utcnow
from .law_ai_models import LawAiDraft
from .main import app, check_csrf, get_db, rate_limit, redirect, render, require

law_user = require("laws")
MAX_UPLOAD = 25 * 1024 * 1024
TEXT_LIMIT = 2 * 1024 * 1024
ORIGINAL_DIR = settings.data_dir / "law-ai-originals"

MIME = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown", ".txt": "text/plain",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".webp": "image/webp",
}


def _validated_filename(name: str, data: bytes) -> tuple[str, str]:
    clean = str(name or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255]
    extension = Path(clean).suffix.lower()
    if not clean or extension not in MIME:
        raise HTTPException(415, "Erlaubt sind PDF, DOCX, Markdown, Text und Bilddateien.")
    signatures = {
        ".pdf": data.startswith(b"%PDF-"),
        ".docx": data.startswith(b"PK\x03\x04"),
        ".png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": data.startswith(b"\xff\xd8\xff"),
        ".jpeg": data.startswith(b"\xff\xd8\xff"),
        ".tif": data.startswith((b"II*\x00", b"MM\x00*")),
        ".tiff": data.startswith((b"II*\x00", b"MM\x00*")),
        ".webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if extension in signatures and not signatures[extension]:
        raise HTTPException(415, "Der Dateiinhalt entspricht nicht dem angegebenen Format.")
    if not data:
        raise HTTPException(400, "Die Datei ist leer.")
    return clean, MIME[extension]


def _text_candidate(filename: str, data: bytes) -> tuple[str, str]:
    if Path(filename).suffix.lower() not in {".md", ".txt"}:
        # This binary never enters a document parser inside the web process.
        return "", "needs_ocr"
    if len(data) > TEXT_LIMIT:
        raise HTTPException(413, "Textdateien dürfen höchstens 2 MB enthalten.")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise HTTPException(415, "Text muss UTF-8-kodiert sein.") from exc
    if "\x00" in decoded:
        raise HTTPException(415, "Binärdaten sind keine Textdatei.")
    return decoded, "staged"


def _original_path(row: LawAiDraft) -> Path:
    if not re.fullmatch(r"[a-f0-9]{48}", row.original_storage_key):
        raise HTTPException(404)
    return ORIGINAL_DIR / row.original_storage_key


def _own(db: Session, draft_id: int, user: User) -> LawAiDraft:
    row = db.get(LawAiDraft, draft_id)
    # Even an unrelated administrator must not browse another editor's staging
    # area without a separately designed and logged delegation flow.
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "Arbeitsentwurf nicht gefunden.")
    return row


def _render(request, db, user, selected=None):
    rows = list(db.scalars(select(LawAiDraft).where(
        LawAiDraft.owner_id == user.id).order_by(LawAiDraft.created_at.desc()).limit(40)))
    response = render(request, "law_ai_workspace.html", user,
                      drafts=rows, selected=selected, doc_types=lx.DOC_TYPES,
                      level_options=lx.level_options(db))
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.get("/laws-assistant")
def law_ai_home(request: Request, user: User = Depends(law_user),
                db: Session = Depends(get_db)):
    return _render(request, db, user)


@app.post("/laws-assistant/import", dependencies=[Depends(check_csrf)])
async def law_ai_import(request: Request, file: UploadFile = File(...),
                        user: User = Depends(law_user),
                        db: Session = Depends(get_db)):
    rate_limit(request, "law-ai-upload", limit=12, window=3600, key=str(user.id))
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Die Datei ist größer als 25 MB.")
    filename, mime = _validated_filename(file.filename or "", data)
    text, status = _text_candidate(filename, data)

    ORIGINAL_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    storage_key = secrets.token_hex(24)
    path = ORIGINAL_DIR / storage_key
    # File names supplied by a user never enter filesystem paths.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        row = LawAiDraft(
            owner_id=user.id, original_filename=filename,
            original_storage_key=storage_key,
            original_sha256=hashlib.sha256(data).hexdigest(),
            original_size=len(data), original_mime=mime,
            proposed_md=text,
            proposed_title=Path(filename).stem.replace("_", " ")[:400],
            status=status,
        )
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return redirect(f"/laws-assistant/{row.id}")


@app.get("/laws-assistant/{draft_id:int}")
def law_ai_review(request: Request, draft_id: int,
                  user: User = Depends(law_user), db: Session = Depends(get_db)):
    return _render(request, db, user, _own(db, draft_id, user))


@app.get("/laws-assistant/{draft_id:int}/original")
def law_ai_original(draft_id: int, user: User = Depends(law_user),
                    db: Session = Depends(get_db)):
    draft = _own(db, draft_id, user)
    path = _original_path(draft)
    if not path.is_file():
        raise HTTPException(404, "Originaldatei nicht vorhanden.")
    return FileResponse(
        path, filename=draft.original_filename, media_type="application/octet-stream",
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.post("/laws-assistant/{draft_id:int}/accept",
          dependencies=[Depends(check_csrf)])
def law_ai_accept(
    request: Request, draft_id: int,
    title: str = Form(""), body_md: str = Form(""),
    doc_type: str = Form("satzung"), level_id: str = Form(""),
    confirmed: str = Form(""), user: User = Depends(law_user),
    db: Session = Depends(get_db),
):
    """Only explicit human confirmation creates a NEW UNPUBLISHED law draft."""
    row = _own(db, draft_id, user)
    if row.status == "accepted":
        raise HTTPException(409, "Dieser Entwurf wurde bereits übernommen.")
    if confirmed != "1":
        raise HTTPException(422, "Bitte zuerst die geprüfte Übernahme ausdrücklich bestätigen.")
    if doc_type not in lx.DOC_TYPES:
        raise HTTPException(422, "Unbekannter Rechtstexttyp.")
    if not title.strip() or len(title.strip()) > 400:
        raise HTTPException(422, "Bitte einen Titel mit maximal 400 Zeichen eingeben.")
    if not body_md.strip() or len(body_md.encode("utf-8")) > TEXT_LIMIT:
        raise HTTPException(422, "Bitte einen geprüften Text mit höchstens 2 MB eintragen.")
    from .routes_laws import _apply
    # Atomic compare-and-swap: repeated/parallel submissions cannot create
    # a second law from the same draft. The database transaction owns the lock.
    acquired = db.execute(update(LawAiDraft).where(
        LawAiDraft.id == draft_id,
        LawAiDraft.owner_id == user.id,
        LawAiDraft.status.in_(("staged", "needs_ocr")),
    ).values(status="accepting", updated_at=utcnow()))
    if acquired.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Der Arbeitsstand wurde inzwischen verarbeitet.")
    law = LawText(created_by=user.id)
    values = {
        "title": title.strip(), "doc_type": doc_type,
        "level_id": level_id, "published": "0", "internal": "0",
        "issued_on": "", "valid_from": "", "valid_until": "",
        "version_note": "Redaktionell übernommener Import",
    }
    failure = _apply(db, law, values, body_md, user)
    if failure:
        db.rollback()
        raise HTTPException(422, failure)
    # The _apply implementation is legacy, so explicitly pin publication off
    # even if it changes later. Publication is a separate authenticated action.
    law.published = False
    db.add(law)
    db.flush()
    lx.store(db, law)
    row.accepted_law_id = law.id
    row.accepted_at = utcnow()
    row.status = "accepted"
    db.commit()
    return redirect(f"/laws/{law.id}/edit")


@app.post("/laws-assistant/{draft_id:int}/discard",
          dependencies=[Depends(check_csrf)])
def law_ai_discard(
    request: Request, draft_id: int, discard_confirmed: str = Form(""),
    user: User = Depends(law_user), db: Session = Depends(get_db),
):
    if discard_confirmed != "1":
        raise HTTPException(422, "Das Verwerfen muss ausdrücklich bestätigt werden.")
    row = _own(db, draft_id, user)
    if row.status == "accepted":
        raise HTTPException(409, "Ein bereits übernommener Originalnachweis darf nicht entfernt werden.")
    path = _original_path(row)
    db.delete(row)
    db.commit()
    path.unlink(missing_ok=True)
    return redirect("/laws-assistant")
