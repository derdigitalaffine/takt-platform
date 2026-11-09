"""Public service dispatcher between real form responses and internal Anliegen.

Route handlers for existing online applications may keep calling workflow.start;
the new API is additive and must not modify their historical behaviour.
"""
from sqlalchemy.orm import Session

from . import workflow
from .anliegen_process_engine import request_start
from .anliegen_process_models import AnliegenProcessRule
from .anliegen_models import Anliegen
from .db import FormResponse, User
from .process_context import ProcessExecutionContext, anliegen_context, form_context


def start(db: Session, context: ProcessExecutionContext, *,
          response: FormResponse | None = None,
          case: Anliegen | None = None,
          rule: AnliegenProcessRule | None = None,
          actor: User | None = None,
          origin: str = "",
          launch_key: str = "",
          inputs: dict | None = None):
    """Dispatch based on explicit object identity, not duck typing.

    Only genuine FormResponse instances may invoke form-specific actions.
    Only genuine Anliegen instances may use the internal executor.
    """
    if not isinstance(context, ProcessExecutionContext):
        raise ValueError("Ein typisierter Prozesskontext ist erforderlich.")
    if context.kind == "form_response":
        if not isinstance(response, FormResponse) or form_context(response) != context:
            raise ValueError("Der Formularvorgang passt nicht zum Prozesskontext.")
        if case is not None or rule is not None:
            raise ValueError("Formular- und Anliegenkontexte dürfen nicht vermischt werden.")
        return workflow.start(db, response)
    if context.kind == "anliegen":
        if not isinstance(case, Anliegen) or anliegen_context(case) != context:
            raise ValueError("Das Anliegen passt nicht zum Prozesskontext.")
        if response is not None or rule is None or actor is None:
            raise ValueError("Unvollständiger Prozesskontext für ein internes Anliegen.")
        return request_start(db, case, rule, actor, origin=origin,
                             launch_key=launch_key, inputs=inputs)
    raise ValueError("Unbekannter Prozesskontext.")
