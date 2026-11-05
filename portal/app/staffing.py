"""Pure headcount conflict calculation for the planned leave workflow.

No authorization or persistence happens here. Callers must supply only authorized,
consistent snapshots and recheck inside the transaction that makes leave binding.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Literal, Mapping

Half = Literal["am", "pm"]


@dataclass(frozen=True)
class Period:
    person_id: int
    start: date
    end: date
    start_half: Half = "am"
    end_half: Half = "pm"

    def __post_init__(self):
        if self.start_half not in ("am", "pm") or self.end_half not in ("am", "pm"):
            raise ValueError("Ungültiger Tagesabschnitt")
        if self.end < self.start or (
            self.end == self.start and self.start_half == "pm" and self.end_half == "am"
        ):
            raise ValueError("Ungültiger Zeitraum")

    def contains(self, day: date, half: Half) -> bool:
        return (
            (self.start, self.start_half == "pm")
            <= (day, half == "pm")
            <= (self.end, self.end_half == "pm")
        )


@dataclass(frozen=True)
class Rule:
    org_id: int
    minimum: int
    mode: Literal["warning", "block"]

    def __post_init__(self):
        if self.minimum < 0 or self.mode not in ("warning", "block"):
            raise ValueError("Ungültige Besetzungsregel")


@dataclass(frozen=True)
class Conflict:
    org_id: int
    day: date
    half: Half
    available: int
    minimum: int
    mode: str
    forecast: bool


def ancestors(org_id: int, parents: Mapping[int, int | None]) -> tuple[int, ...]:
    result = []
    while org_id is not None:
        if org_id in result or org_id not in parents:
            raise ValueError("Ungültige Organisationshierarchie")
        result.append(org_id)
        org_id = parents[org_id]
    return tuple(result)


def check_headcount(
    *,
    candidate: Period,
    memberships: Iterable[tuple[int, int, bool]],
    parents: Mapping[int, int | None],
    rules: Iterable[Rule],
    unavailable: Iterable[Period],
    tentative: Iterable[Period] = (),
    working: Mapping[int, set[tuple[date, Half]]] | None = None
) -> list[Conflict]:
    """Compare binding headcount and a separate forecast for each affected unit.

    Membership rows are (person, org, counts_staff); a person counts only once
    in any ancestor even when several assignments reach it. ``working`` can
    explicitly restrict scheduled half-days; None means simple all-days mode.
    Callers must supply closure-day exceptions and active persons in their snapshot.
    """
    if (candidate.end - candidate.start).days > 400:
        raise ValueError("Zeitraum zu lang")
    staff: dict[int, set[int]] = {}
    for person, org, counts in memberships:
        if counts:
            for unit in ancestors(org, parents):
                staff.setdefault(unit, set()).add(person)
    existing, forecasts = list(unavailable), list(tentative)
    affected = [
        rule for rule in rules if candidate.person_id in staff.get(rule.org_id, set())
    ]
    results = []
    for offset in range((candidate.end - candidate.start).days + 1):
        day = candidate.start + timedelta(days=offset)
        for half in ("am", "pm"):
            if not candidate.contains(day, half):
                continue
            active = lambda person: working is None or (day, half) in working.get(
                person, set()
            )
            if not active(candidate.person_id):
                continue
            absent = {p.person_id for p in existing if p.contains(day, half)} | {
                candidate.person_id
            }
            forecast_absent = absent | {
                p.person_id for p in forecasts if p.contains(day, half)
            }
            for rule in affected:
                available_people = {
                    person for person in staff[rule.org_id] if active(person)
                }
                if working is not None and not available_people:
                    continue
                binding_count = len(available_people - absent)
                forecast_count = len(available_people - forecast_absent)
                if binding_count < rule.minimum:
                    results.append(
                        Conflict(
                            rule.org_id,
                            day,
                            half,
                            binding_count,
                            rule.minimum,
                            rule.mode,
                            False,
                        )
                    )
                if forecast_count < rule.minimum and forecast_count != binding_count:
                    results.append(
                        Conflict(
                            rule.org_id,
                            day,
                            half,
                            forecast_count,
                            rule.minimum,
                            rule.mode,
                            True,
                        )
                    )
    return results
