"""Offline-only MarkItDown + Tesseract processor for TAKT Ortsrecht.

An entirely separate container reads only uploaded originals and tiny signed-by-path
job manifests from its dedicated mounts. No DB/portal secrets, no outgoing network.
Its JSON output is always an untrusted *proposal* for human review.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ORIGINALS = Path(os.environ.get("LAW_OCR_ORIGINALS", "/work/originals"))
QUEUE = Path(os.environ.get("LAW_OCR_QUEUE", "/work/queue"))
RESULTS = Path(os.environ.get("LAW_OCR_RESULTS", "/work/results"))
ALLOWED_SUFFIXES = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
KEY_RE = re.compile(r"^[0-9a-f]{48}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 25 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024
MAX_PAGES = 120
MAX_PIXELS = 12_000_000
MAX_WORDS = 30000
MAX_TSV_BYTES = 3 * 1024 * 1024


class OcrFailure(Exception):
    """Redacted, safe worker error; do not include source text in messages."""


def _check_input(job: dict, job_key: str, originals: Path) -> tuple[Path, str]:
    if not isinstance(job, dict) or not KEY_RE.fullmatch(job_key):
        raise OcrFailure("Ungültige Auftragskennung.")
    storage = job.get("storage_key")
    suffix = job.get("extension")
    sha = job.get("sha256")
    byte_size = job.get("size")
    if (not isinstance(storage, str) or not KEY_RE.fullmatch(storage)
            or suffix not in ALLOWED_SUFFIXES or not isinstance(sha, str)
            or not SHA_RE.fullmatch(sha) or type(byte_size) is not int
            or not 0 < byte_size <= MAX_BYTES):
        raise OcrFailure("Ungültiger OCR-Auftrag.")
    original = originals / storage
    if original.is_symlink() or not original.is_file():
        raise OcrFailure("Originaldatei nicht gefunden.")
    actual = hashlib.sha256()
    size = 0
    with original.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            size += len(block)
            if size > MAX_BYTES:
                raise OcrFailure("Originaldatei überschreitet die Sicherheitsgrenze.")
            actual.update(block)
    if actual.hexdigest() != sha or size != byte_size:
        raise OcrFailure("Prüfsumme oder Größe des Originals stimmen nicht.")
    return original, suffix


def _markdown(path: Path) -> str:
    """MarkItDown with no plugins, no LLM client and no remote conversion."""
    try:
        from markitdown import MarkItDown
        engine = MarkItDown(enable_plugins=False)
        result = engine.convert_local(str(path))
        text = result.text_content or ""
    except Exception as exc:
        raise OcrFailure("MarkItDown konnte das Dokument nicht umwandeln.") from exc
    if len(text.encode("utf-8")) > MAX_TEXT:
        raise OcrFailure("Die MarkItDown-Ausgabe ist zu umfangreich.")
    return text.strip()


def _tsv_words(tsv: str) -> tuple[str, float | None, list[dict]]:
    """Preserve word locations and confidence; never guess missing OCR values."""
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t")
    lines: dict[tuple[int, int, int, int], list[str]] = {}
    positions = []
    scores = []
    for index, word in enumerate(reader):
        if index > MAX_WORDS:
            raise OcrFailure("Die OCR-Ausgabe enthält zu viele Worteinträge.")
        text = (word.get("text") or "").strip()
        if not text:
            continue
        try:
            key = tuple(int(word[k]) for k in ("page_num", "block_num", "par_num", "line_num"))
            confidence = float(word.get("conf") or -1)
            left, top, width, height = (int(word.get(k) or 0)
                                        for k in ("left", "top", "width", "height"))
        except (ValueError, TypeError) as exc:
            raise OcrFailure("Die OCR-Positionsdaten sind ungültig.") from exc
        if any(v < 0 for v in (left, top, width, height)):
            continue
        lines.setdefault(key, []).append(text)
        if 0 <= confidence <= 100:
            scores.append(confidence)
        if len(positions) < 2500:
            positions.append({"text": text[:80], "x": left, "y": top,
                              "w": width, "h": height,
                              "confidence": round(confidence, 1) if confidence >= 0 else None})
    text = "\n".join(" ".join(line) for _, line in sorted(lines.items())).strip()
    return text, round(sum(scores) / len(scores), 1) if scores else None, positions


def _tesseract(png: bytes, language: str = "deu") -> tuple[str, float | None, list[dict]]:
    """Bounded subprocess, argument list only; never execute document-provided commands."""
    if language not in ("deu", "deu+eng"):
        raise OcrFailure("Nicht unterstützte OCR-Sprache.")
    if len(png) > 22 * 1024 * 1024:
        raise OcrFailure("Gerenderte Seite zu groß.")
    try:
        done = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", language, "tsv"],
            input=png, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=75, check=False,
            env={"PATH": "/usr/bin:/bin", "OMP_THREAD_LIMIT": "1", "HOME": "/tmp"},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise OcrFailure("Tesseract ist nicht verfügbar oder hat das Zeitlimit überschritten.") from exc
    if done.returncode or len(done.stdout) > MAX_TSV_BYTES:
        raise OcrFailure("Tesseract konnte die Seite nicht zuverlässig auswerten.")
    return _tsv_words(done.stdout.decode("utf-8", "replace"))


def _pdf(path: Path, language: str) -> tuple[str, list[dict], list[str]]:
    try:
        import fitz
        pdf = fitz.open(str(path))
    except Exception as exc:
        raise OcrFailure("PDF konnte nicht sicher gelesen werden.") from exc
    pages = []
    warnings = []
    with pdf:
        if pdf.needs_pass:
            raise OcrFailure("Passwortgeschütztes PDF; bitte zunächst entschlüsseln.")
        if pdf.page_count > MAX_PAGES:
            raise OcrFailure("PDF überschreitet die zulässige Seitenzahl.")
        for i in range(pdf.page_count):
            page = pdf.load_page(i)
            native = page.get_text("text", sort=True).strip()
            if len(native) >= 80:
                pages.append({"page": i + 1, "engine": "native-pdf", "text": native[:MAX_TEXT],
                              "confidence": None, "words": []})
                continue
            width = int(page.rect.width * 2)
            height = int(page.rect.height * 2)
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise OcrFailure("PDF-Seite hat eine unzulässige Bildgröße.")
            bitmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            recognized, confidence, positions = _tesseract(bitmap.tobytes("png"), language)
            pages.append({"page": i + 1, "engine": "tesseract", "text": recognized,
                          "confidence": confidence, "words": positions})
            if confidence is None or confidence < 75:
                warnings.append(f"Seite {i+1}: OCR unsicher, Original manuell prüfen.")
    if not pages:
        raise OcrFailure("PDF enthält keine Seiten.")
    # MarkItDown gives better headings, lists and tables on a fully digital PDF;
    # for hybrid scans preserve the page order and OCR source mapping instead.
    if all(p["engine"] == "native-pdf" for p in pages):
        try:
            markdown = _markdown(path)
        except OcrFailure:
            warnings.append("MarkItDown-Konvertierung nicht möglich; Textseiten verwendet.")
            markdown = ""
        if len(markdown) < 20:
            markdown = "\n\n".join(p["text"] for p in pages)
    else:
        markdown = "\n\n".join(
            f"<!-- OCR-Quelle: Seite {p['page']}, Verfahren {p['engine']} -->\n\n{p['text']}"
            for p in pages
        )
        if any(p["engine"] == "native-pdf" for p in pages):
            warnings.append("Gemischtes PDF: Struktur aus nativen Seiten und OCR-Seiten manuell vergleichen.")
    return markdown, pages, warnings


def _image(path: Path, language: str) -> tuple[str, list[dict], list[str]]:
    try:
        from PIL import Image
        with Image.open(path) as picture:
            count = getattr(picture, "n_frames", 1)
            if count > MAX_PAGES:
                raise OcrFailure("Bild enthält zu viele Seiten.")
            pages = []
            for i in range(count):
                picture.seek(i)
                if picture.width * picture.height > MAX_PIXELS:
                    raise OcrFailure("Bild überschreitet die Pixelgrenze.")
                frame = picture.convert("RGB")
                stream = io.BytesIO()
                frame.save(stream, format="PNG")
                text, score, positions = _tesseract(stream.getvalue(), language)
                pages.append({"page": i + 1, "engine": "tesseract", "text": text,
                              "confidence": score, "words": positions})
    except OcrFailure:
        raise
    except Exception as exc:
        raise OcrFailure("Bild kann nicht sicher ausgewertet werden.") from exc
    return ("\n\n".join(p["text"] for p in pages), pages,
            [f"Seite {p['page']}: OCR manuell prüfen."
             for p in pages if p["confidence"] is None or p["confidence"] < 75])


def extract(original: Path, suffix: str, language: str = "deu") -> dict:
    """One bounded execution; never treat generated Markdown as legal authority."""
    if suffix not in ALLOWED_SUFFIXES:
        raise OcrFailure("Dateiformat nicht unterstützt.")
    with tempfile.TemporaryDirectory(prefix="law-ocr-") as temporary:
        path = Path(temporary) / ("document" + suffix)
        shutil.copyfile(original, path)
        if suffix == ".docx":
            md = _markdown(path)
            pages = [{"page": 1, "engine": "markitdown-docx", "text": md[:2000],
                      "confidence": None, "words": []}]
            warnings = ["DOCX besitzt keine stabilen Originalseiten; Text und Tabellen manuell prüfen."]
        elif suffix == ".pdf":
            md, pages, warnings = _pdf(path, language)
        else:
            md, pages, warnings = _image(path, language)
    if len(md.encode("utf-8")) > MAX_TEXT:
        raise OcrFailure("Erkannter Text überschreitet die Textgrenze.")
    if not md.strip():
        raise OcrFailure("Kein lesbarer Text gefunden; Original manuell prüfen.")
    return {"markdown": md, "pages": pages,
            "warnings": warnings + ["Automatisch extrahiert, keine rechtsverbindliche Fassung."]}


def _atomic_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 15 * 1024 * 1024:
        raise OcrFailure("OCR-Ergebnis überschreitet die Ausgabegrenze.")
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("xb") as destination:
        destination.write(payload)
    os.replace(tmp, path)


def process(job_path: Path) -> None:
    key = job_path.name.split(".", 1)[0]
    result = {"schema": 1, "job_key": key, "status": "failed",
              "message": "Dokument konnte nicht ausgewertet werden."}
    try:
        if not KEY_RE.fullmatch(key) or job_path.stat().st_size > 8192:
            raise OcrFailure("Ungültige Jobdatei.")
        job = json.loads(job_path.read_text("utf-8"))
        original, suffix = _check_input(job, key, ORIGINALS)
        result["sha256"] = job["sha256"]
        output = extract(original, suffix, job.get("language", "deu"))
        result.update({"status": "done", **output})
        result.pop("message", None)
    except (OcrFailure, ValueError, OSError, KeyError, TypeError) as exc:
        # Do not log source text, raw converter output or other personal data.
        if isinstance(exc, OcrFailure):
            result["message"] = str(exc)[:180]
    if KEY_RE.fullmatch(key):
        _atomic_json(RESULTS / (key + ".result.json"), result)
    job_path.unlink(missing_ok=True)


def run_forever() -> None:
    for directory in (QUEUE, RESULTS):
        directory.mkdir(parents=True, exist_ok=True)
    # Recover interrupted tasks on restart without requiring DB credentials.
    for old in QUEUE.glob("*.work.json"):
        old.replace(QUEUE / (old.name[:48] + ".job.json"))
    while True:
        found = False
        for path in sorted(QUEUE.glob("*.job.json"))[:10]:
            key = path.name.split(".", 1)[0]
            if not KEY_RE.fullmatch(key):
                continue
            processing = QUEUE / (key + ".work.json")
            try:
                path.rename(processing)
            except OSError:
                continue
            found = True
            process(processing)
        if not found:
            time.sleep(2)


if __name__ == "__main__":
    run_forever()
