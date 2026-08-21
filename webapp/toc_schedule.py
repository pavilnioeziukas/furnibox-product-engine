from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable

from webapp.toc_odoo import AssemblyCandidate


PRIORITY_RULE_VERSION = "mq005-v1"
PRIORITY_LABELS = {
    1: "Vėluojantis READY",
    2: "READY + SKUBUS",
    3: "Kitas READY",
}


@dataclass(frozen=True)
class PlanEntry:
    rank: int
    so_reference: str
    priority_level: int
    priority_label: str
    delivery_date: str | None
    urgent: bool
    readiness_date: str
    assembly_hours: float
    cumulative_hours: float
    planned_today: bool


def generate_daily_plan(
    candidates: Iterable[AssemblyCandidate],
    readiness_states: dict[str, dict[str, Any]],
    *, business_date: date, capacity_hours: float,
) -> list[PlanEntry]:
    if capacity_hours < 0:
        raise ValueError("Capacity cannot be negative.")
    ranked: list[tuple[tuple[Any, ...], AssemblyCandidate, date]] = []
    for candidate in candidates:
        state = readiness_states.get(candidate.so_reference) or {}
        if state.get("status") != "ready":
            continue
        readiness_date = state.get("readiness_date")
        if not isinstance(readiness_date, date):
            continue
        if candidate.delivery_date and candidate.delivery_date < business_date:
            level = 1
        elif candidate.urgent:
            level = 2
        else:
            level = 3
        key = (
            level,
            candidate.delivery_date or date.max,
            readiness_date,
            candidate.so_reference,
        )
        ranked.append((key, candidate, readiness_date))
    ranked.sort(key=lambda item: item[0])

    result: list[PlanEntry] = []
    cumulative = 0.0
    for rank, (key, candidate, readiness_date) in enumerate(ranked, start=1):
        planned_today = cumulative < capacity_hours
        cumulative = round(cumulative + candidate.assembly_hours, 2)
        level = int(key[0])
        result.append(PlanEntry(
            rank=rank, so_reference=candidate.so_reference,
            priority_level=level, priority_label=PRIORITY_LABELS[level],
            delivery_date=candidate.delivery_date.isoformat() if candidate.delivery_date else None,
            urgent=candidate.urgent, readiness_date=readiness_date.isoformat(),
            assembly_hours=candidate.assembly_hours, cumulative_hours=cumulative,
            planned_today=planned_today,
        ))
    return result


def serialize_plan(entries: Iterable[PlanEntry]) -> list[dict[str, Any]]:
    return [asdict(entry) for entry in entries]
