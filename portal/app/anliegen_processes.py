"""Fail-closed policy primitives for linking Anliegen to published process versions.

No side effects, no process execution and no external/AI calls. Used by the
incremental internal-process rollout and future authorization boundary.
"""
from collections.abc import Mapping
from .db import Setting

START_MODES = frozenset({"submit", "handler", "auto"})
COMPLETION_MODES = frozenset({"manual", "all_success", "any_success"})
DEFAULT_POLICY = {
    "start_modes": [],
    "approval_required": True,
    "completion": "manual",
    "agent_autonomy": "off",
    "field_mapping": [],
    "dependencies": [],
}


def integration_enabled(db) -> bool:
    """Explicit, independent opt-in. Absence of a setting means OFF."""
    value = db.get(Setting, "anliegen_process_integration_enabled")
    return bool(value and value.value == "1")


def normalize_policy(raw: Mapping) -> dict:
    """Validate a versioned policy; reject unknown and unsafe keys rather than guessing."""
    if not isinstance(raw, Mapping):
        raise ValueError("Die Prozesskonfiguration muss ein Objekt sein.")
    unknown = set(raw) - set(DEFAULT_POLICY)
    if unknown:
        raise ValueError("Unbekannte Prozesskonfiguration.")
    modes = raw.get("start_modes", [])
    if not isinstance(modes, list) or any(m not in START_MODES for m in modes):
        raise ValueError("Unbekannte Startart.")
    if len(modes) != len(set(modes)):
        raise ValueError("Startarten dürfen nicht doppelt sein.")
    approval = raw.get("approval_required", True)
    if not isinstance(approval, bool):
        raise ValueError("Freigabepflicht muss ein Wahrheitswert sein.")
    completion = raw.get("completion", "manual")
    if completion not in COMPLETION_MODES:
        raise ValueError("Unbekannte Abschlussregel.")
    autonomy = raw.get("agent_autonomy", "off")
    if autonomy not in ("off", "advice", "suggest"):
        # Autonomous execution requires a separate, audited action-specific grant.
        raise ValueError("Autonome KI-Ausführung ist nicht pauschal freigebbar.")
    mapping = raw.get("field_mapping", [])
    if not isinstance(mapping, list) or len(mapping) > 64:
        raise ValueError("Ungültige Feldzuordnung.")
    cleaned = []
    for item in mapping:
        if (not isinstance(item, dict) or set(item) != {"source", "target"}
                or not all(isinstance(item[k], str) and 1 <= len(item[k]) <= 64
                           and item[k].replace("_", "").isalnum() for k in ("source", "target"))):
            raise ValueError("Ungültige Feldzuordnung.")
        if item["source"] in ("description_enc", "title_enc", "confidential"):
            raise ValueError("Geschützte Felder können nicht implizit übertragen werden.")
        cleaned.append(dict(item))
    dependencies = raw.get("dependencies", [])
    validate_dependencies(dependencies)
    return {"start_modes": sorted(modes), "approval_required": approval,
            "completion": completion, "agent_autonomy": autonomy,
            "field_mapping": cleaned, "dependencies": [dict(d) for d in dependencies]}


def validate_dependencies(edges: list) -> None:
    """Reject dangling/ambiguous edges and cycles before a rule can be activated."""
    if not isinstance(edges, list) or len(edges) > 128:
        raise ValueError("Ungültige Prozessabhängigkeiten.")
    graph = {}
    for edge in edges:
        if (not isinstance(edge, dict) or set(edge) != {"before", "after"}
                or not all(isinstance(edge[k], str) and 1 <= len(edge[k]) <= 64
                           for k in ("before", "after"))):
            raise ValueError("Ungültige Prozessabhängigkeit.")
        a, b = edge["before"], edge["after"]
        if a == b:
            raise ValueError("Ein Prozess darf nicht von sich selbst abhängen.")
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set())
    visiting, visited = set(), set()
    def visit(node):
        if node in visiting:
            raise ValueError("Zyklische Prozessabhängigkeit.")
        if node in visited:
            return
        visiting.add(node)
        for neighbour in graph[node]:
            visit(neighbour)
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
