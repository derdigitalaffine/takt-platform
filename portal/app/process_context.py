"""Typed context boundary shared by form and internal Anliegen workflows.

A process definition is generic; the execution adapter is not. FormResponse
effects (applicant mail, tracking URLs, DMS, payment) MUST NOT be used for Anliegen.
"""
from dataclasses import dataclass
from typing import Literal

from .db import FormResponse
from .anliegen_models import Anliegen


@dataclass(frozen=True)
class ProcessExecutionContext:
    kind: Literal["form_response", "anliegen"]
    object_id: int
    requester_id: int | None
    assignee_id: int | None
    org_id: int | None
    confidential: bool


def form_context(response: FormResponse) -> ProcessExecutionContext:
    if not isinstance(response, FormResponse) or response.id is None:
        raise ValueError("Gültiger Formularantrag erforderlich.")
    return ProcessExecutionContext("form_response", response.id, response.user_id,
                                   response.assignee_id, None, False)


def anliegen_context(case: Anliegen) -> ProcessExecutionContext:
    if not isinstance(case, Anliegen) or case.id is None:
        raise ValueError("Gültiges internes Anliegen erforderlich.")
    return ProcessExecutionContext("anliegen", case.id, case.reporter_id,
                                   case.assignee_id, case.org_id, case.confidential)
