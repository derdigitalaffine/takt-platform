"""Retention lifecycle for stored personal KI conversations."""
from datetime import timedelta

from sqlalchemy import select

from .ai_models import AIConversation
from .db import SessionLocal, get_settings, utcnow


def purge_expired() -> int:
    """Purge chats beyond the configured retention period, including messages.

    The existing worker invokes this periodically. Only current database rows
    are removed; database backups follow their separate retention policy.
    """
    with SessionLocal() as db:
        try:
            days = int(get_settings(db).get("ai_retention_days", "90"))
        except (ValueError, TypeError):
            days = 90
        days = max(1, min(days, 3650))
        cutoff = utcnow() - timedelta(days=days)
        old = list(db.scalars(select(AIConversation).where(AIConversation.updated_at < cutoff)
                              .limit(500)))
        for item in old:
            db.delete(item)
        db.commit()
        return len(old)
