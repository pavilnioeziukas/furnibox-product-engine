from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from webapp.toc_odoo import AssemblyCandidate


PRIORITY_RULE_VERSION = "mq005-v2"
LOCAL_TIMEZONE = ZoneInfo("Europe/Vilnius")
WORK_START = time(7, 0)
LUNCH_START = time(12, 0)
LUNCH_END = time(13, 0)
WORK_END = time(16, 0)
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
    worker_lane: int | None
    planned_start: str | None
    planned_end: str | None
    continues_next_day: bool


def _next_workday(value: date) -> date:
    value += timedelta(days=1)
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def _normalize_work_start(value: datetime) -> datetime:
    current = value.timetz().replace(tzinfo=None)
    if value.weekday() >= 5 or current >= WORK_END:
        return datetime.combine(_next_workday(value.date()), WORK_START, LOCAL_TIMEZONE)
    if current < WORK_START:
        return datetime.combine(value.date(), WORK_START, LOCAL_TIMEZONE)
    if LUNCH_START <= current < LUNCH_END:
        return datetime.combine(value.date(), LUNCH_END, LOCAL_TIMEZONE)
    return value


def _add_productive_hours(start: datetime, hours: float) -> datetime:
    current = _normalize_work_start(start)
    remaining = timedelta(hours=hours)
    while remaining > timedelta(0):
        current = _normalize_work_start(current)
        clock = current.timetz().replace(tzinfo=None)
        window_end = datetime.combine(
            current.date(), LUNCH_START if clock < LUNCH_START else WORK_END, LOCAL_TIMEZONE,
        )
        available = window_end - current
        if remaining <= available:
            return current + remaining
        remaining -= available
        current = (
            datetime.combine(current.date(), LUNCH_END, LOCAL_TIMEZONE)
            if window_end.timetz().replace(tzinfo=None) == LUNCH_START
            else datetime.combine(_next_workday(current.date()), WORK_START, LOCAL_TIMEZONE)
        )
    return current


def generate_daily_plan(
    candidates: Iterable[AssemblyCandidate],
    readiness_states: dict[str, dict[str, Any]],
    *, business_date: date, capacity_hours: float, employee_count: int | None = None,
) -> list[PlanEntry]:
    if capacity_hours < 0:
        raise ValueError("Capacity cannot be negative.")
    ranked: list[tuple[tuple[Any, ...], AssemblyCandidate, date]] = []
    for candidate in candidates:
        if not candidate.system_ready:
            continue
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

    if employee_count is None:
        employee_count = int(capacity_hours // 8)
    if employee_count < 0:
        raise ValueError("Employee count cannot be negative.")
    lane_available = [
        datetime.combine(business_date, WORK_START, LOCAL_TIMEZONE)
        for _ in range(employee_count)
    ]
    result: list[PlanEntry] = []
    cumulative = 0.0
    for rank, (key, candidate, readiness_date) in enumerate(ranked, start=1):
        cumulative = round(cumulative + candidate.assembly_hours, 2)
        level = int(key[0])
        if lane_available:
            lane_index = min(range(len(lane_available)), key=lambda index: (lane_available[index], index))
            planned_start_dt = _normalize_work_start(lane_available[lane_index])
            planned_end_dt = _add_productive_hours(planned_start_dt, candidate.assembly_hours)
            lane_available[lane_index] = planned_end_dt
            worker_lane = lane_index + 1
            planned_today = planned_start_dt.date() == business_date
            planned_start = planned_start_dt.isoformat(timespec="minutes")
            planned_end = planned_end_dt.isoformat(timespec="minutes")
            continues_next_day = planned_end_dt.date() != planned_start_dt.date()
        else:
            worker_lane = None
            planned_today = False
            planned_start = planned_end = None
            continues_next_day = False
        result.append(PlanEntry(
            rank=rank, so_reference=candidate.so_reference,
            priority_level=level, priority_label=PRIORITY_LABELS[level],
            delivery_date=candidate.delivery_date.isoformat() if candidate.delivery_date else None,
            urgent=candidate.urgent, readiness_date=readiness_date.isoformat(),
            assembly_hours=candidate.assembly_hours, cumulative_hours=cumulative,
            planned_today=planned_today,
            worker_lane=worker_lane, planned_start=planned_start, planned_end=planned_end,
            continues_next_day=continues_next_day,
        ))
    return result


def serialize_plan(entries: Iterable[PlanEntry]) -> list[dict[str, Any]]:
    return [asdict(entry) for entry in entries]
