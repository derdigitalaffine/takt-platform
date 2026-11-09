"""Contract tests for the fail-closed internal process integration foundation."""
import pytest
from sqlalchemy import inspect
from app.anliegen_processes import integration_enabled, normalize_policy, validate_dependencies


def test_process_integration_is_opt_in(db):
    assert integration_enabled(db) is False
    for table in ("anliegen_process_rules", "anliegen_process_runs", "anliegen_process_audit"):
        assert inspect(db.bind).has_table(table)


def test_process_policy_defaults_to_manual_review_and_no_agent(db):
    config = normalize_policy({})
    assert config["start_modes"] == []
    assert config["approval_required"] is True
    assert config["completion"] == "manual"
    assert config["agent_autonomy"] == "off"


def test_explicit_launch_modes_are_validated():
    p = normalize_policy({"start_modes": ["handler", "submit"],
                          "field_mapping": [{"source": "title", "target": "subject"}]})
    assert p["start_modes"] == ["handler", "submit"]
    with pytest.raises(ValueError):
        normalize_policy({"start_modes": ["submit", "submit"]})
    with pytest.raises(ValueError):
        normalize_policy({"start_modes": ["everyone"]})
    with pytest.raises(ValueError):
        normalize_policy({"agent_autonomy": "execute"})


def test_sensitive_fields_not_auto_mapped():
    for field in ("title_enc", "description_enc", "confidential"):
        with pytest.raises(ValueError):
            normalize_policy({"field_mapping": [{"source": field, "target": "external"}]})
    with pytest.raises(ValueError):
        normalize_policy({"upload_all_attachments": True})


def test_dependency_cycle_and_self_loop_rejected():
    validate_dependencies([{"before": "budget", "after": "order"},
                           {"before": "order", "after": "setup"}])
    for edges in (
        [{"before": "a", "after": "a"}],
        [{"before": "a", "after": "b"}, {"before": "b", "after": "a"}],
        [{"before": "a", "after": "b"}, {"before": "b", "after": "c"},
         {"before": "c", "after": "a"}],
    ):
        with pytest.raises(ValueError):
            validate_dependencies(edges)
