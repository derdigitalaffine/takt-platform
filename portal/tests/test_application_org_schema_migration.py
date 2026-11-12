"""Regression for the production hotfix: a pre-existing form DB missed app_org_id.

PR #373 accidentally registered app_org_id in the legacy migration for
"groups", although the SQLAlchemy model requires it in "forms". The app
can start but authenticated dashboard and form ORM queries then fail with 500.
"""
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app import db as model


def test_legacy_form_schema_is_repaired_without_losing_existing_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-forms.sqlite'}")
    # Existing production data already has the rest of the schema, but is
    # missing the new org foreign key on the forms table.
    model.Base.metadata.create_all(engine)
    with Session(engine) as session:
        existing = model.Form(title="Bestehender Antrag", kind="application",
                              app_prefix="ALT", app_group_id=None)
        session.add(existing)
        session.commit()
        form_id = existing.id

    with engine.begin() as conn:
        # Newly-created test schema has the ORM index; older production did
        # not, as its app_org_id column was missing entirely.
        conn.execute(text("DROP INDEX IF EXISTS ix_forms_app_org_id"))
        conn.execute(text("ALTER TABLE forms DROP COLUMN app_org_id"))
        # The incorrect previous migration may already have written this
        # extra (unused) group column. It must not prevent repair.
        conn.execute(text(
            "ALTER TABLE groups ADD COLUMN app_org_id "
            "INTEGER REFERENCES organizations(id) ON DELETE SET NULL"))
    assert "app_org_id" not in {c["name"] for c in inspect(engine).get_columns("forms")}

    monkeypatch.setattr(model, "engine", engine)
    model._migrate()
    assert "app_org_id" in {c["name"] for c in inspect(engine).get_columns("forms")}
    assert "org_id" in {c["name"] for c in inspect(engine).get_columns("groups")}

    # Startup migrates repeatedly without creating duplicate columns; all
    # former application settings and records still read through the ORM.
    model._migrate()
    with Session(engine) as session:
        same_form = session.scalar(select(model.Form).where(model.Form.id == form_id))
        assert same_form is not None
        assert same_form.title == "Bestehender Antrag"
        assert same_form.kind == "application"
        assert same_form.app_prefix == "ALT"
        assert same_form.app_group_id is None
        assert same_form.app_org_id is None
        same_form.app_org_id = None
        session.commit()


def test_application_responsibility_is_migrated_on_correct_model_table():
    assert "app_org_id" in model.Form.__table__.columns
    assert "app_org_id" in model._NEW_COLUMNS["forms"]
    assert "app_org_id" not in model._NEW_COLUMNS["groups"]
    assert "responsible_org_id" in model._NEW_COLUMNS["form_responses"]
    assert "responsible_org_id" in model._NEW_COLUMNS["application_tasks"]
