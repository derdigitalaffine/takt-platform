"""Liveness and migration readiness must be distinguishable during deployment."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import main
from conftest import client


def _schema(engine, *, draft_ocr=True, agents=True):
    with engine.begin() as conn:
        optional = ", ocr_job_key VARCHAR(48)" if draft_ocr else ""
        conn.execute(text("CREATE TABLE law_ai_drafts (id INTEGER PRIMARY KEY"
                          + optional
                          + ", ocr_pages_json TEXT, ocr_warnings_json TEXT, ocr_failure VARCHAR(180))"))
        if agents:
            conn.execute(text("""
                CREATE TABLE law_ai_analyses (
                    id INTEGER PRIMARY KEY, draft_id INTEGER,
                    source_sha256 VARCHAR(64), provider_map_json TEXT,
                    status VARCHAR(16), retry_attempts INTEGER NOT NULL DEFAULT 0
                )
            """))


def test_portal_readiness_detects_legacy_missing_ocr_column(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old-schema.db'}")
    try:
        _schema(engine, draft_ocr=False)
        monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
        status = client().get("/readyz")
        assert status.status_code == 503
        assert status.text == "not ready"
        assert status.headers["cache-control"] == "no-store"
        assert "ocr_job_key" not in status.text  # no schema details leak
    finally:
        engine.dispose()


def test_portal_readiness_detects_missing_agent_table(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'no-agents.db'}")
    try:
        _schema(engine, agents=False)
        monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
        status = client().get("/readyz")
        assert status.status_code == 503
        assert status.text == "not ready"
    finally:
        engine.dispose()


def test_portal_readiness_passes_after_compatible_migration(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'upgraded.db'}")
    try:
        _schema(engine)
        monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
        response = client().get("/readyz")
        assert response.status_code == 200
        assert response.text == "ok"
        assert response.headers["cache-control"] == "no-store"
    finally:
        engine.dispose()


def test_portal_readiness_detects_missing_json_recovery_migration(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'missing-retry.db'}")
    try:
        _schema(engine)
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE law_ai_analyses DROP COLUMN retry_attempts"))
        monkeypatch.setattr(main, "SessionLocal", sessionmaker(bind=engine))
        response = client().get("/readyz")
        assert response.status_code == 503
        assert response.text == "not ready"
    finally:
        engine.dispose()


def test_liveness_and_favicon_survive_domain_mapping_database_failure(monkeypatch):
    def fail_db_lookup():
        raise RuntimeError("Module-domain mapping DB unavailable")
    monkeypatch.setattr(main, "module_hosts", fail_db_lookup)
    c = client()
    alive = c.get("/healthz")
    assert alive.status_code == 200
    assert alive.text == "ok"
    # An absent favicon can return normal 404. It must not return 500 just
    # because this DB-backed host-routing middleware cannot load its map.
    favicon = c.get("/favicon.ico")
    assert favicon.status_code == 404
