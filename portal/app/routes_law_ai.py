"""Safe Ortsrecht intake: immutable originals, human-reviewed unpublished drafts.

This deliberately has NO LLM execution, OCR, external fetch, or publication path.
Untrusted binary PDFs/DOCX/images are staged for the future isolated worker.
"""
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import laws as lx, law_ai_agents, law_ai_agent_jobs, law_ai_coverage
from .config import settings
from .db import LawText, User, utcnow, get_settings
from .law_ai_models import LawAiDraft
from .law_ai_agent_models import LawAiAnalysis
from .main import app, check_csrf, get_db, rate_limit, redirect, render, require

law_user = require("laws")
MAX_UPLOAD = 25 * 1024 * 1024
TEXT_LIMIT = 2 * 1024 * 1024
ORIGINAL_DIR = settings.data_dir / "law-ai-originals"
OCR_QUEUE = settings.data_dir / "law-ai-ocr-queue"
OCR_RESULTS = settings.data_dir / "law-ai-ocr-results"

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


def _render(request, db, user, selected=None, bereich="uebersicht"):
    if bereich not in ("uebersicht", "import", "ki", "editor"):
        bereich = "uebersicht"
    rows = list(db.scalars(select(LawAiDraft).where(
        LawAiDraft.owner_id == user.id).order_by(LawAiDraft.created_at.desc()).limit(40)))
    try:
        ocr_pages = json.loads(selected.ocr_pages_json or "[]") if selected else []
        ocr_warnings = json.loads(selected.ocr_warnings_json or "[]") if selected else []
    except (ValueError, TypeError):
        ocr_pages, ocr_warnings = [], []
    cfg = get_settings(db)
    ai_enabled = user.can("ai_chat") and cfg.get("module_ai") == "1" and cfg.get("module_laws") == "1"
    agent_routes = {}
    if ai_enabled:
        for task, _label in law_ai_agents.STAGES:
            agent_routes.update(law_ai_agent_jobs.configured_routes(db, (task,)))
    analysis = (db.scalar(select(LawAiAnalysis).where(
        LawAiAnalysis.draft_id == selected.id,
        LawAiAnalysis.requested_by == user.id,
    ).order_by(LawAiAnalysis.id.desc()).limit(1)) if selected else None)
    analysis_current = bool(
        analysis and selected and
        analysis.source_sha256 == law_ai_agents.source_hash(selected.proposed_md or "")
    )
    analysis_results = {}
    advanced_sections = 0
    if selected and selected.status in ("staged", "ocr_review") and selected.proposed_md:
        try:
            advanced_sections = len(law_ai_coverage.sections(selected.proposed_md))
        except ValueError:
            pass
    if analysis and analysis.status == "done" and analysis_current:
        for key, field in (("structure", "outline_json"), ("metadata", "metadata_json"),
                           ("verification", "verification_json")):
            try:
                decoded = json.loads(getattr(analysis, field) or "{}")
                analysis_results[key] = decoded if isinstance(decoded, dict) else {}
            except ValueError:
                analysis_results[key] = {}
    response = render(request, "law_ai_workspace.html", user,
                      drafts=rows, selected=selected, bereich=bereich,
                      doc_types=lx.DOC_TYPES,
                      ocr_pages=ocr_pages if isinstance(ocr_pages, list) else [],
                      ocr_warnings=ocr_warnings if isinstance(ocr_warnings, list) else [],
                      analysis=analysis, analysis_current=analysis_current,
                      analysis_results=analysis_results, advanced_sections=advanced_sections,
                      max_model_calls=advanced_sections * len(law_ai_agents.STAGES),
                      ai_enabled=ai_enabled,
                      agent_routes=agent_routes, agent_stages=law_ai_agents.STAGES,
                      ai_source_limit=law_ai_agents.MAX_SOURCE_CHARS,
                      level_options=lx.level_options(db))
    response.headers["Cache-Control"] = "private, no-store"
    return response



def _safe_job_key(key: str) -> bool:
    return bool(re.fullmatch(r"[a-f0-9]{48}", key or ""))


def _apply_ocr_result(db: Session, draft: LawAiDraft) -> bool:
    """Import a completed worker result, never modify or publish LawText."""
    if draft.status != "ocr_queued" or not _safe_job_key(draft.ocr_job_key):
        return False
    path = OCR_RESULTS / (draft.ocr_job_key + ".result.json")
    if not path.is_file():
        return False
    if path.stat().st_size > 15 * 1024 * 1024:
        raise HTTPException(502, "Das OCR-Ergebnis ist zu groß.")
    try:
        result = json.loads(path.read_text("utf-8"))
    except (ValueError, UnicodeError):
        raise HTTPException(502, "Das OCR-Ergebnis ist beschädigt.") from None
    if (not isinstance(result, dict) or result.get("schema") != 1
            or result.get("job_key") != draft.ocr_job_key
            or result.get("sha256") != draft.original_sha256
            or result.get("status") not in ("done", "failed")):
        raise HTTPException(502, "OCR-Ergebnis stimmt nicht mit dem Original überein.")
    changes = {"updated_at": utcnow()}
    if result["status"] == "done":
        text = result.get("markdown")
        pages = result.get("pages")
        warnings = result.get("warnings")
        if (not isinstance(text, str) or not 0 < len(text.encode("utf-8")) <= TEXT_LIMIT
                or not isinstance(pages, list) or len(pages) > 120
                or not isinstance(warnings, list) or len(warnings) > 150):
            raise HTTPException(502, "Das OCR-Ergebnis enthält ungültige Daten.")
        # Only human-readable evidence, and a bounded selection of word boxes.
        summary = []
        for page in pages:
            if not isinstance(page, dict):
                raise HTTPException(502, "OCR-Seitendaten haben ein ungültiges Format.")
            boxes = page.get("words", [])
            summary.append({
                "page": page.get("page"),
                "engine": str(page.get("engine", ""))[:30],
                "confidence": page.get("confidence"),
                "text_excerpt": str(page.get("text", ""))[:300],
                "words": boxes[:200] if isinstance(boxes, list) else [],
            })
        changes.update(status="ocr_review", proposed_md=text,
                       ocr_pages_json=json.dumps(summary, ensure_ascii=False),
                       ocr_warnings_json=json.dumps([str(w)[:200] for w in warnings],
                                                    ensure_ascii=False),
                       ocr_failure="")
    else:
        changes.update(status="ocr_failed",
                       ocr_failure=str(result.get("message") or
                                       "Texterkennung fehlgeschlagen.")[:180])
    # CAS protects a pending manual action from overwriting a reviewed result.
    updated = db.execute(update(LawAiDraft).where(
        LawAiDraft.id == draft.id, LawAiDraft.status == "ocr_queued",
        LawAiDraft.ocr_job_key == draft.ocr_job_key,
    ).values(**changes))
    if updated.rowcount != 1:
        db.rollback()
        return False
    db.commit()
    db.refresh(draft)
    path.unlink(missing_ok=True)
    return True


@app.post("/laws-assistant/{draft_id:int}/ocr", dependencies=[Depends(check_csrf)])
def law_ai_queue_ocr(
    request: Request, draft_id: int,
    language: str = Form("deu"),
    user: User = Depends(law_user), db: Session = Depends(get_db),
):
    """Explicit request; the web app never parses untrusted binary documents."""
    rate_limit(request, "law-ai-ocr-queue", limit=6, window=3600, key=str(user.id))
    row = _own(db, draft_id, user)
    if row.status not in ("needs_ocr", "ocr_failed"):
        raise HTTPException(409, "Der Entwurf ist nicht für eine neue OCR vorgesehen.")
    if language not in ("deu", "deu+eng"):
        raise HTTPException(422, "Nicht unterstützte OCR-Sprache.")
    extension = Path(row.original_filename).suffix.lower()
    if extension not in {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
        raise HTTPException(415, "Für dieses Format ist keine Texterkennung vorgesehen.")
    if not _original_path(row).is_file():
        raise HTTPException(404, "Originaldatei fehlt.")
    job_key = secrets.token_hex(24)
    job = {
        "job_key": job_key,
        "storage_key": row.original_storage_key,
        "extension": extension, "sha256": row.original_sha256,
        "size": row.original_size, "language": language,
    }
    acquired = db.execute(update(LawAiDraft).where(
        LawAiDraft.id == row.id, LawAiDraft.owner_id == user.id,
        LawAiDraft.status.in_(("needs_ocr", "ocr_failed")),
    ).values(status="ocr_queued", ocr_job_key=job_key, ocr_failure="",
             updated_at=utcnow()))
    if acquired.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Der Entwurf wird bereits verarbeitet.")
    OCR_QUEUE.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = OCR_QUEUE / (job_key + ".tmp")
    submitted = OCR_QUEUE / (job_key + ".job.json")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(job, output, ensure_ascii=False)
        os.replace(temporary, submitted)
        db.commit()
    except Exception:
        db.rollback()
        temporary.unlink(missing_ok=True)
        submitted.unlink(missing_ok=True)
        raise
    return redirect(f"/laws-assistant/{row.id}?bereich={'ki' if status == 'staged' else 'import'}")


def _ocr_phase(draft: LawAiDraft) -> dict:
    """Bounded, privacy-safe phase from worker file names; no directory scan.

    File queue is intentionally an offline protocol, not a real-time page
    progress API. Do not claim percentages or worker availability.
    """
    phase = "not_required"
    message = "Keine Texterkennung beauftragt."
    elapsed = 0
    attention = False
    if draft.status == "ocr_queued":
        key = draft.ocr_job_key
        if _safe_job_key(key):
            if (OCR_QUEUE / (key + ".work.json")).is_file():
                phase, message = "processing", "Offline-Texterkennung verarbeitet das Dokument."
            elif (OCR_QUEUE / (key + ".job.json")).is_file():
                phase, message = "queued", "Auftrag wartet in der Offline-Warteschlange."
            elif (OCR_RESULTS / (key + ".result.json")).is_file():
                phase, message = "finalizing", "OCR-Ergebnis wird für die Prüfung eingelesen."
            else:
                phase, message = "unknown", "OCR-Auftrag ist noch nicht erreichbar; Worker und Queue prüfen."
        else:
            phase, message = "unknown", "OCR-Auftragskennung nicht verfügbar."
        try:
            elapsed = min(86400, max(0, int((utcnow() - draft.updated_at).total_seconds())))
        except (AttributeError, TypeError, ValueError):
            elapsed = 0
        attention = phase in ("queued", "unknown") and elapsed >= 600
    elif draft.status == "ocr_review":
        phase, message = "review", "OCR-Vorschlag liegt zur manuellen Kontrolle bereit."
    elif draft.status == "ocr_failed":
        phase, message = "failed", "Die Texterkennung ist fehlgeschlagen."
    return {"phase": phase, "phase_message": message,
            "elapsed_seconds": elapsed, "needs_attention": attention}


@app.get("/laws-assistant/{draft_id:int}/ocr/status")
def law_ai_ocr_status(
    draft_id: int, user: User = Depends(law_user), db: Session = Depends(get_db),
):
    from fastapi.responses import JSONResponse
    row = _own(db, draft_id, user)
    _apply_ocr_result(db, row)
    return JSONResponse({
        "status": row.status,
        "ready": row.status in ("ocr_review", "ocr_failed"),
        "failure": row.ocr_failure if row.status == "ocr_failed" else "",
        **_ocr_phase(row),
    }, headers={"Cache-Control": "private, no-store"})

@app.get("/laws-assistant")
def law_ai_home(request: Request, bereich: str = "uebersicht", user: User = Depends(law_user),
                db: Session = Depends(get_db)):
    return _render(request, db, user, bereich=bereich)


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
def law_ai_review(request: Request, draft_id: int, bereich: str = "uebersicht",
                  user: User = Depends(law_user), db: Session = Depends(get_db)):
    row = _own(db, draft_id, user)
    _apply_ocr_result(db, row)
    return _render(request, db, user, row, bereich=bereich)


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


@app.post("/laws-assistant/markdown/review", dependencies=[Depends(check_csrf)])
def law_ai_review_markdown(
    body_md: str = Form(""),
    user: User = Depends(law_user),
):
    """Read-only, permission-checked validation of the current editor buffer.

    The response is a suggested heading-only transformation. No original,
    import draft, or published law is ever changed by this endpoint.
    """
    from fastapi.responses import JSONResponse
    from .law_ai_markdown import review

    try:
        result = review(body_md)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/laws-assistant/{draft_id:int}/accept",
          dependencies=[Depends(check_csrf)])
def law_ai_accept(
    request: Request, draft_id: int,
    title: str = Form(""), body_md: str = Form(""),
    doc_type: str = Form("satzung"), level_id: str = Form(""),
    short_title: str = Form(""), version_note: str = Form(""),
    issued_on: str = Form(""), valid_from: str = Form(""),
    valid_until: str = Form(""), confirmed: str = Form(""),
    user: User = Depends(law_user),
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
    if db.scalar(select(LawAiAnalysis.id).where(
        LawAiAnalysis.draft_id == draft_id,
        LawAiAnalysis.status.in_(("queued", "running"))).limit(1)) is not None:
        raise HTTPException(409, "Eine KI-Analyse läuft noch. Bitte vorher abschließen oder abbrechen.")
    from .routes_laws import _apply
    # Atomic compare-and-swap: repeated/parallel submissions cannot create
    # a second law from the same draft. The database transaction owns the lock.
    acquired = db.execute(update(LawAiDraft).where(
        LawAiDraft.id == draft_id,
        LawAiDraft.owner_id == user.id,
        LawAiDraft.status.in_(("staged", "needs_ocr", "ocr_review", "ocr_failed")),
    ).values(status="accepting", updated_at=utcnow()))
    if acquired.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Der Arbeitsstand wurde inzwischen verarbeitet.")
    law = LawText(created_by=user.id)
    values = {
        "title": title.strip(), "doc_type": doc_type,
        "level_id": level_id, "published": "0", "internal": "0",
        "short_title": short_title[:80],
        "issued_on": issued_on, "valid_from": valid_from, "valid_until": valid_until,
        "version_note": version_note[:255] or "Redaktionell übernommener Import",
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
    if row.status not in ("staged", "needs_ocr", "ocr_review", "ocr_failed"):
        raise HTTPException(409, "Dieser Arbeitsstand kann nicht gelöscht werden.")
    if row.status == "ocr_queued":
        raise HTTPException(409, "OCR-Auftrag läuft noch. Nach Abschluss kann der Entwurf verworfen werden.")
    if db.scalar(select(LawAiAnalysis.id).where(
            LawAiAnalysis.draft_id == draft_id,
            LawAiAnalysis.status.in_(("queued", "running"))).limit(1)) is not None:
        raise HTTPException(409, "Laufende KI-Analyse zuerst abschließen oder abbrechen.")
    path = _original_path(row)
    db.delete(row)
    db.commit()
    path.unlink(missing_ok=True)
    return redirect("/laws-assistant")
