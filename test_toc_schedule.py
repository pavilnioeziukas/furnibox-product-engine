from datetime import date, datetime

from webapp.toc_odoo import AssemblyCandidate
from webapp.toc_schedule import generate_daily_plan


def candidate(so, due, urgent=False, hours=4):
    return AssemblyCandidate(so, due, urgent, hours, 1, system_ready=True)


def test_plan_excludes_physical_ready_order_when_odoo_is_not_ready():
    item = AssemblyCandidate("S1", date(2026, 8, 22), False, 4, 1, system_ready=False)

    plan = generate_daily_plan(
        [item], {"S1": {"status": "ready", "readiness_date": date(2026, 8, 20)}},
        business_date=date(2026, 8, 21), capacity_hours=8,
    )

    assert plan == []


def test_plan_applies_approved_mq005_order_and_ready_tie_breaker():
    candidates = [
        candidate("S-LATE-NEW", date(2026, 8, 19), hours=3),
        candidate("S-LATE-OLD", date(2026, 8, 18), hours=3),
        candidate("S-URGENT", date(2026, 8, 25), urgent=True),
        candidate("S-NORMAL-EARLY-READY", date(2026, 8, 24)),
        candidate("S-NORMAL-LATE-READY", date(2026, 8, 24)),
        candidate("S-NOT-READY", date(2026, 8, 17)),
    ]
    states = {
        "S-LATE-NEW": {"status": "ready", "readiness_date": date(2026, 8, 21)},
        "S-LATE-OLD": {"status": "ready", "readiness_date": date(2026, 8, 21)},
        "S-URGENT": {"status": "ready", "readiness_date": date(2026, 8, 21)},
        "S-NORMAL-EARLY-READY": {"status": "ready", "readiness_date": date(2026, 8, 20)},
        "S-NORMAL-LATE-READY": {"status": "ready", "readiness_date": date(2026, 8, 21)},
        "S-NOT-READY": {"status": "not_ready", "readiness_date": date(2026, 8, 18)},
    }

    plan = generate_daily_plan(candidates, states, business_date=date(2026, 8, 21), capacity_hours=16)

    assert [item.so_reference for item in plan] == [
        "S-LATE-OLD", "S-LATE-NEW", "S-URGENT",
        "S-NORMAL-EARLY-READY", "S-NORMAL-LATE-READY",
    ]
    assert [item.priority_level for item in plan] == [1, 1, 2, 3, 3]


def test_job_that_starts_inside_capacity_is_in_today_plan_even_if_it_spills_over():
    candidates = [candidate("S1", date(2026, 8, 22), hours=6), candidate("S2", date(2026, 8, 23), hours=4)]
    states = {
        "S1": {"status": "ready", "readiness_date": date(2026, 8, 20)},
        "S2": {"status": "ready", "readiness_date": date(2026, 8, 20)},
    }

    plan = generate_daily_plan(candidates, states, business_date=date(2026, 8, 21), capacity_hours=8)

    assert [item.planned_today for item in plan] == [True, True]
    assert plan[-1].cumulative_hours == 10
    assert plan[0].planned_start.endswith("07:00+03:00")
    assert plan[0].planned_end.endswith("14:00+03:00")
    assert plan[1].planned_start.endswith("14:00+03:00")
    assert plan[1].planned_end.startswith("2026-08-24T09:00")
    assert plan[1].continues_next_day is True


def test_three_workers_receive_parallel_whole_so_lanes():
    candidates = [candidate("S1", date(2026, 8, 22), hours=11), candidate("S2", date(2026, 8, 23), hours=4), candidate("S3", date(2026, 8, 24), hours=5), candidate("S4", date(2026, 8, 25), hours=2)]
    states = {item.so_reference: {"status": "ready", "readiness_date": date(2026, 8, 20)} for item in candidates}

    plan = generate_daily_plan(
        candidates, states, business_date=date(2026, 8, 21),
        capacity_hours=24, employee_count=3,
    )

    assert [item.worker_lane for item in plan] == [1, 2, 3, 2]
    assert [datetime.fromisoformat(item.planned_start).strftime("%H:%M") for item in plan] == [
        "07:00", "07:00", "07:00", "11:00",
    ]
    assert plan[0].planned_end.startswith("2026-08-24T10:00")
    assert plan[0].continues_next_day is True


def test_zero_capacity_places_no_job_in_today_plan():
    plan = generate_daily_plan(
        [candidate("S1", date(2026, 8, 22))],
        {"S1": {"status": "ready", "readiness_date": date(2026, 8, 20)}},
        business_date=date(2026, 8, 21), capacity_hours=0,
    )

    assert plan[0].planned_today is False
