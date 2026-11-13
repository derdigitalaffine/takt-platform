"""Central, backwards-compatible task-to-model resolution for TAKT agents.

A missing assignment retains legacy behaviour. An explicitly assigned but inactive
provider fails closed; it must never silently fall back to another data recipient.
Secrets are not exposed to callers or serialized by this module.
"""
from types import SimpleNamespace

from sqlalchemy import select

from .ai_models import AIProvider, AITaskProfile
from .ai_provider import AIProviderError

TASKS = {
    "chat": "TAKT-Chat · Standard für neue Unterhaltungen",
    "portal_plan": "Portalaufträge · /takt-Planung",
    "form_draft": "Formulare · KI-Formularassistent",
    "anliegen_draft": "Interne Anliegen · KI-Entwürfe",
    "law_ocr_vision": "Ortsrecht · Vision-/OCR-Korrektur",
    "law_structure": "Ortsrecht · Gliederung und Formatierung",
    "law_metadata": "Ortsrecht · Stammdatenextraktion",
    "law_verify": "Ortsrecht · Texttreue und Gegenprüfung",
}


def select_provider(db, task: str, *, fallback=None):
    """Resolve a task profile to a safe provider view; never mutate ORM objects.

    The caller remains responsible for its existing module, user and source ACLs.
    An absent assignment preserves the previous provider selection, including a
    user's explicit conversation choice.
    """
    if task not in TASKS:
        raise ValueError("Unbekannte KI-Aufgabe.")
    assignment = db.get(AITaskProfile, task)
    if assignment is None:
        provider = fallback or db.scalar(select(AIProvider).where(
            AIProvider.active.is_(True)).order_by(AIProvider.id))
        if provider is None or not provider.active:
            raise AIProviderError("Für diese KI-Aufgabe ist kein aktiver Provider verfügbar.")
        return provider

    provider = db.get(AIProvider, assignment.provider_id)
    if provider is None or not provider.active:
        raise AIProviderError("Der für diese KI-Aufgabe zugewiesene Provider ist nicht aktiv.")
    return SimpleNamespace(
        id=provider.id, name=provider.name, base_url=provider.base_url,
        model_id=assignment.model_id or provider.model_id,
        text_key_enc=provider.text_key_enc, image_key_enc=provider.image_key_enc,
        active=provider.active, stream_enabled=provider.stream_enabled,
        allow_private=provider.allow_private, timeout_seconds=provider.timeout_seconds,
    )
