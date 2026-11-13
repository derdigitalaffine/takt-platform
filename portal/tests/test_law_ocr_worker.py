"""Offline worker unit tests: provenance, MarkItDown, Tesseract and boundaries."""
import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

from ocr_worker import worker


def test_tesseract_tsv_preserves_coordinates_and_confidence():
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t12\t91.5\tSatzung\n"
        "5\t1\t1\t1\t1\t2\t45\t20\t15\t12\t78.5\t2026\n"
        "5\t1\t1\t1\t2\t1\t10\t44\t30\t12\t99\t§\n"
    )
    text, score, boxes = worker._tsv_words(tsv)
    assert text == "Satzung 2026\n§"
    assert score == pytest.approx(89.7)
    assert boxes[0] == {"text": "Satzung", "x": 10, "y": 20, "w": 30, "h": 12,
                        "confidence": 91.5}


def test_source_hash_and_file_path_are_strict(tmp_path):
    original = b"irrelevant binary, only the worker reads it"
    key = "a" * 48
    filename = tmp_path / key
    filename.write_bytes(original)
    job = {"storage_key": key, "extension": ".docx",
           "sha256": hashlib.sha256(original).hexdigest(), "size": len(original)}
    resolved, suffix = worker._check_input(job, "b" * 48, tmp_path)
    assert resolved == filename and suffix == ".docx"
    with pytest.raises(worker.OcrFailure):
        worker._check_input({**job, "storage_key": "../shadow"}, "b" * 48, tmp_path)
    with pytest.raises(worker.OcrFailure):
        worker._check_input({**job, "sha256": "0" * 64}, "b" * 48, tmp_path)
    with pytest.raises(worker.OcrFailure):
        worker._check_input({**job, "size": len(original) + 1}, "b" * 48, tmp_path)


def test_docx_uses_markitdown_without_network_or_llm(monkeypatch, tmp_path):
    original = tmp_path / "word.docx"
    original.write_bytes(b"simple test")
    seen = []
    monkeypatch.setattr(worker, "_markdown",
                        lambda path: seen.append(path.suffix) or
                        "# Normwerk\n\n| Betrag |\n| --- |\n| 10 € |")
    result = worker.extract(original, ".docx")
    assert seen == [".docx"]
    assert "| Betrag |" in result["markdown"]
    assert result["pages"][0]["engine"] == "markitdown-docx"
    assert "keine stabilen Originalseiten" in " ".join(result["warnings"])


def test_mixed_pdf_combines_native_pages_and_tesseract(monkeypatch, tmp_path):
    class Page:
        def __init__(self, native):
            self.native = native
            self.rect = SimpleNamespace(width=100, height=100)

        def get_text(self, *_args, **_kwargs):
            return self.native

        def get_pixmap(self, **_kwargs):
            return SimpleNamespace(tobytes=lambda format: b"png")

    class PDF:
        needs_pass = False
        page_count = 2

        def __enter__(self): return self
        def __exit__(self, *a): return None

        def load_page(self, i):
            return Page(("Satzungstext " * 15) if i == 0 else "")

    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(
        open=lambda _: PDF(), Matrix=lambda x, y: (x, y),
    ))
    monkeypatch.setattr(worker, "_tesseract",
                        lambda png, language: ("§ 2: Die Gebühr beträgt 10 €.", 64.0,
                                                [{"text": "10", "x": 10, "y": 30,
                                                  "w": 12, "h": 8, "confidence": 64.0}]))
    original = tmp_path / "mixed.pdf"
    original.write_bytes(b"pdf")
    result = worker.extract(original, ".pdf")
    assert len(result["pages"]) == 2
    assert [page["engine"] for page in result["pages"]] == ["native-pdf", "tesseract"]
    assert "§ 2" in result["markdown"]
    assert result["pages"][1]["page"] == 2
    assert "OCR-Quelle" not in result["markdown"]
    assert any("unsicher" in note for note in result["warnings"])


def test_worker_produces_result_without_modifying_original(monkeypatch, tmp_path):
    original_dir = tmp_path / "originals"
    queue_dir = tmp_path / "queue"
    result_dir = tmp_path / "results"
    for d in (original_dir, queue_dir, result_dir):
        d.mkdir()
    monkeypatch.setattr(worker, "ORIGINALS", original_dir)
    monkeypatch.setattr(worker, "QUEUE", queue_dir)
    monkeypatch.setattr(worker, "RESULTS", result_dir)
    source = b"original is immutable"
    source_key, job_key = "a" * 48, "b" * 48
    (original_dir / source_key).write_bytes(source)
    request = {"job_key": job_key, "storage_key": source_key,
               "extension": ".docx", "size": len(source),
               "sha256": hashlib.sha256(source).hexdigest(), "language": "deu"}
    path = queue_dir / (job_key + ".work.json")
    path.write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(worker, "extract", lambda *_args, **_kw:
                        {"markdown": "# Genehmigung\n\n§ 1 Text",
                         "pages": [{"page": 1, "engine": "markitdown-docx",
                                    "confidence": None, "text": "Text", "words": []}],
                         "warnings": ["Text prüfen"]})
    worker.process(path)
    result = json.loads((result_dir / (job_key + ".result.json")).read_text("utf-8"))
    assert result["status"] == "done"
    assert result["sha256"] == request["sha256"]
    assert result["markdown"].startswith("#")
    assert not path.exists()
    assert (original_dir / source_key).read_bytes() == source


def test_worker_reports_hash_failure_without_ingesting_data(monkeypatch, tmp_path):
    original_dir = tmp_path / "originals"
    queue_dir = tmp_path / "queue"
    result_dir = tmp_path / "results"
    for directory in (original_dir, queue_dir, result_dir):
        directory.mkdir()
    monkeypatch.setattr(worker, "ORIGINALS", original_dir)
    monkeypatch.setattr(worker, "QUEUE", queue_dir)
    monkeypatch.setattr(worker, "RESULTS", result_dir)
    source = b"one version"
    storage_key, job_key = "a" * 48, "b" * 48
    (original_dir / storage_key).write_bytes(source)
    job = {"storage_key": storage_key, "extension": ".pdf",
           "size": len(source), "sha256": "0" * 64}
    path = queue_dir / (job_key + ".work.json")
    path.write_text(json.dumps(job))
    worker.process(path)
    result = json.loads((result_dir / (job_key + ".result.json")).read_text())
    assert result["status"] == "failed"
    assert result["sha256"] == "0" * 64
    assert "Prüfsumme" in result["message"]
