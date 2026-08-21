from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from webapp.toc_odoo import AssemblyCandidate


@dataclass(frozen=True)
class DailyConstraintSignal:
    code: str
    label: str
    conclusion: str
    action: str
    capacity_hours: float | None
    total_load_hours: float
    odoo_ready_hours: float
    final_ready_hours: float
    odoo_blocked_hours: float
    physical_pending_hours: float
    physical_blocked_hours: float


def _hours(values: Iterable[AssemblyCandidate]) -> float:
    return round(sum(item.assembly_hours for item in values), 2)


def diagnose_daily_constraint_signal(
    candidates: Iterable[AssemblyCandidate],
    readiness_states: dict[str, dict[str, Any]],
    *, capacity_hours: float | None,
) -> DailyConstraintSignal:
    candidates = tuple(candidates)
    odoo_ready = tuple(item for item in candidates if item.system_ready)
    odoo_blocked = tuple(item for item in candidates if not item.system_ready)
    final_ready = tuple(
        item for item in odoo_ready
        if (readiness_states.get(item.so_reference) or {}).get("status") == "ready"
    )
    physical_blocked = tuple(
        item for item in odoo_ready
        if (readiness_states.get(item.so_reference) or {}).get("status") == "not_ready"
    )
    physical_pending = tuple(
        item for item in odoo_ready
        if (readiness_states.get(item.so_reference) or {}).get("status") not in {"ready", "not_ready"}
    )
    values = {
        "capacity_hours": capacity_hours,
        "total_load_hours": _hours(candidates),
        "odoo_ready_hours": _hours(odoo_ready),
        "final_ready_hours": _hours(final_ready),
        "odoo_blocked_hours": _hours(odoo_blocked),
        "physical_pending_hours": _hours(physical_pending),
        "physical_blocked_hours": _hours(physical_blocked),
    }

    if capacity_hours is None:
        return DailyConstraintSignal(
            code="INSUFFICIENT_DATA", label="TRŪKSTA DUOMENŲ",
            conclusion="Nepatvirtintas šiandienos Assembly pajėgumas, todėl operacinio signalo išvesti negalima.",
            action="Patvirtinti šiandien dirbančių Assembly darbuotojų skaičių.",
            **values,
        )
    if values["total_load_hours"] < capacity_hours:
        return DailyConstraintSignal(
            code="LOAD_BELOW_CAPACITY", label="KRŪVIS MAŽESNIS UŽ PAJĖGUMĄ",
            conclusion=(
                f"Bendras nepradėtas Assembly krūvis yra {values['total_load_hours']} val., "
                f"o pajėgumas – {capacity_hours} val. Šiandienos signalas nerodo Assembly pajėgumo apribojimo."
            ),
            action="Patikrinti paklausos ir darbų paleidimo srautą; nedidinti Assembly pajėgumo pagal šį signalą.",
            **values,
        )
    if values["final_ready_hours"] < capacity_hours:
        shortage = round(capacity_hours - values["final_ready_hours"], 2)
        return DailyConstraintSignal(
            code="ASSEMBLY_STARVATION_RISK", label="ASSEMBLY BADAVIMO RIZIKA",
            conclusion=(
                f"Šiandienos C yra {capacity_hours} val., o galutinai READY darbo – "
                f"{values['final_ready_hours']} val. Trūksta {shortage} val. paruošto darbo. "
                "Tai yra šiandienos upstream pasirengimo signalas, o ne patvirtintas sistemos constraint."
            ),
            action="Pirmiausia užbaigti fizines patikras ir šalinti didžiausią READY blokuojančią priežastį.",
            **values,
        )
    return DailyConstraintSignal(
        code="READY_LOAD_COVERS_CAPACITY", label="READY KRŪVIS DENGIA PAJĖGUMĄ",
        conclusion=(
            f"Galutinai READY darbo yra {values['final_ready_hours']} val., todėl šiandienos "
            f"{capacity_hours} val. Assembly pajėgumas yra padengtas. Vien šis signalas dar neįrodo, "
            "kad Assembly yra sistemos constraint."
        ),
        action="Apsaugoti READY eilę, vykdyti patvirtintą SCHEDULE ir kaupti faktinius CONTROL nuokrypius.",
        **values,
    )
