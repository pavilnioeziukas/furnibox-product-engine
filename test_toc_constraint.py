from datetime import date

from webapp.toc_constraint import diagnose_daily_constraint_signal
from webapp.toc_odoo import AssemblyCandidate


def item(so, hours, *, system_ready=True):
    return AssemblyCandidate(so, date(2026, 8, 22), False, hours, 1, system_ready=system_ready)


def test_requires_confirmed_capacity_before_diagnosis():
    result = diagnose_daily_constraint_signal([item("S1", 10)], {}, capacity_hours=None)
    assert result.code == "INSUFFICIENT_DATA"


def test_distinguishes_daily_starvation_signal_from_system_constraint():
    candidates = [item("READY", 10), item("PENDING", 8), item("ODOO-BLOCKED", 12, system_ready=False)]
    states = {"READY": {"status": "ready"}, "PENDING": {"status": "unchecked"}}

    result = diagnose_daily_constraint_signal(candidates, states, capacity_hours=24)

    assert result.code == "ASSEMBLY_STARVATION_RISK"
    assert result.final_ready_hours == 10
    assert result.physical_pending_hours == 8
    assert result.odoo_blocked_hours == 12
    assert "ne patvirtintas sistemos constraint" in result.conclusion


def test_ready_load_covering_capacity_is_only_a_constraint_candidate_signal():
    candidates = [item("S1", 14), item("S2", 12)]
    states = {"S1": {"status": "ready"}, "S2": {"status": "ready"}}

    result = diagnose_daily_constraint_signal(candidates, states, capacity_hours=24)

    assert result.code == "READY_LOAD_COVERS_CAPACITY"
    assert result.final_ready_hours == 26
    assert "dar neįrodo" in result.conclusion


def test_total_load_below_capacity_is_not_called_an_assembly_constraint():
    result = diagnose_daily_constraint_signal(
        [item("S1", 8)], {"S1": {"status": "ready"}}, capacity_hours=24,
    )
    assert result.code == "LOAD_BELOW_CAPACITY"
