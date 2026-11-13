"""Regression: an already deployed Ortsrecht staging database must survive OCR upgrade.

Fresh test DBs hide missing migrations because create_all() sees all current ORM
columns. Simulate the 2026-11-13 initial staging schema on a separate SQLite
file and execute exactly the production migration path without touching the
normal portal test database.
"""
from sqlalchemy import create_engine, inspect, text

from app import db as portal_db


OCR_COLUMNS = {
    "ocr_job_key": "",
    "ocr_pages_json": "[]",
    "ocr_warnings_json": "[]",
    "ocr_failure": "",
}


def test_old_ortsrecht_draft_schema_is_extended_without_losing_work(tmp_path, monkeypatch):
    database = tmp_path / "pre_ocr_portal.db"
    engine = create_engine(f"sqlite:///{database}")
    try:
        portal_db.Base.metadata.create_all(engine)
        with engine.begin() as connection:
            # Simulate a real SQLite database created by PR #435 before the
            # four OCR fields were added by PR #438.
            for column in OCR_COLUMNS:
                connection.execute(text(f"ALTER TABLE law_ai_drafts DROP COLUMN {column}"))
            connection.execute(text("""
                INSERT INTO law_ai_drafts
                (id, owner_id, original_filename, original_storage_key,
                 original_sha256, original_size, original_mime,
                 proposed_md, proposed_title, status, created_at, updated_at)
                VALUES
                (77, 1, 'Hausordnung.md', :storage, :sha, 28, 'text/markdown',
                 '# Hausordnung\n\n§ 1 Test', 'Hausordnung', 'staged',
                 '2026-11-13 09:00:00', '2026-11-13 09:00:00')
            """), {"storage": "a" * 48, "sha": "b" * 64})

        old = {c["name"] for c in inspect(engine).get_columns("law_ai_drafts")}
        assert not old.intersection(OCR_COLUMNS)

        # The real migration operates against the production engine. Patch
        # only that handle to exercise it against the private fixture DB.
        monkeypatch.setattr(portal_db, "engine", engine)
        portal_db._migrate()
        portal_db._migrate()  # Must remain safe across repeated app restarts.

        new = {c["name"] for c in inspect(engine).get_columns("law_ai_drafts")}
        assert new.issuperset(OCR_COLUMNS)

        with engine.connect() as connection:
            row = connection.execute(text("""
                SELECT id, original_filename, original_sha256, proposed_md,
                       status, ocr_job_key, ocr_pages_json,
                       ocr_warnings_json, ocr_failure
                FROM law_ai_drafts WHERE id = 77
            """)).one()
        assert row.id == 77
        assert row.original_filename == "Hausordnung.md"
        assert row.original_sha256 == "b" * 64
        assert row.proposed_md == "# Hausordnung\n\n§ 1 Test"
        assert row.status == "staged"
        assert [row.ocr_job_key, row.ocr_pages_json,
                row.ocr_warnings_json, row.ocr_failure] == ["", "[]", "[]", ""]
    finally:
        engine.dispose()
