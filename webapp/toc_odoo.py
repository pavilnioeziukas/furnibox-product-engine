from __future__ import annotations

import os
import xmlrpc.client
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


ALLOWED_METHODS = frozenset({"search_read"})
PENDING_ASSEMBLY_STATES = ("waiting", "ready")


class OdooReader(Protocol):
    def search_read(
        self, model: str, domain: list[Any], fields: list[str], *,
        order: str = "id asc", limit: int = 5000,
    ) -> list[dict[str, Any]]: ...


class ReadOnlyOdooReader:
    """Minimal Odoo reader that rejects every non-approved object method."""

    def __init__(self, *, url: str, database: str, login: str, api_key: str):
        self.database = database
        self.login = login
        self.api_key = api_key
        self.common = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/common", allow_none=True)
        self.models = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/object", allow_none=True)
        self.uid: int | None = None

    @classmethod
    def from_env(cls) -> "ReadOnlyOdooReader":
        values = {
            name: os.getenv(name, "").strip()
            for name in ("ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_API_KEY")
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError("Trūksta Odoo nustatymų: " + ", ".join(missing))
        return cls(
            url=values["ODOO_URL"], database=values["ODOO_DB"],
            login=values["ODOO_LOGIN"], api_key=values["ODOO_API_KEY"],
        )

    def _authenticate(self) -> None:
        uid = self.common.authenticate(self.database, self.login, self.api_key, {})
        if not uid:
            raise PermissionError("Odoo autentifikacija nepavyko.")
        self.uid = int(uid)

    def _call(self, model: str, method: str, args: list[Any], kwargs: dict[str, Any]):
        if method not in ALLOWED_METHODS:
            raise PermissionError(f"Odoo metodas uždraustas: {method}")
        if self.uid is None:
            self._authenticate()
        return self.models.execute_kw(
            self.database, self.uid, self.api_key, model, method, args, kwargs,
        )

    def search_read(
        self, model: str, domain: list[Any], fields: list[str], *,
        order: str = "id asc", limit: int = 5000,
    ) -> list[dict[str, Any]]:
        return self._call(
            model, "search_read", [domain],
            {"fields": fields, "order": order, "limit": limit},
        )


@dataclass(frozen=True)
class AssemblyCandidate:
    so_reference: str
    delivery_date: date | None
    urgent: bool
    assembly_hours: float
    manufacturing_order_count: int
    system_ready: bool = False
    system_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateResult:
    candidates: tuple[AssemblyCandidate, ...]
    read_at: str
    excluded_without_exact_so: int


@dataclass(frozen=True)
class PlanExecutionStatus:
    so_reference: str
    status: str
    label: str
    assembly_workorders: int
    completed_workorders: int


def _relation_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    return int(value) if isinstance(value, int) else None


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def load_assembly_candidates(reader: OdooReader) -> CandidateResult:
    workcenters = reader.search_read(
        "mrp.workcenter", ["|", ["name", "ilike", "Assembly"], ["name", "ilike", "Surink"]],
        ["name"], limit=20,
    )
    workcenter_ids = [int(item["id"]) for item in workcenters]
    if len(workcenter_ids) != 1:
        raise ValueError(f"Tikėtasi vieno aktyvaus Assembly darbo centro, rasta: {len(workcenter_ids)}.")

    workorders = reader.search_read(
        "mrp.workorder",
        [["workcenter_id", "in", workcenter_ids], ["state", "in", list(PENDING_ASSEMBLY_STATES)]],
        ["production_id", "state", "duration_expected"], limit=5000,
    )
    production_ids = sorted({
        relation_id for row in workorders
        if (relation_id := _relation_id(row.get("production_id"))) is not None
    })
    productions = reader.search_read(
        "mrp.production", [["id", "in", production_ids]],
        ["name", "origin", "state"], limit=5000,
    ) if production_ids else []
    production_by_id = {int(item["id"]): item for item in productions}
    so_names = sorted({
        str(item["origin"]).strip() for item in productions if item.get("origin")
    })
    sales = reader.search_read(
        "sale.order", [["name", "in", so_names]],
        ["name", "commitment_date", "tag_ids", "state"], limit=5000,
    ) if so_names else []
    sales_by_name = {str(item["name"]): item for item in sales}
    urgent_tags = reader.search_read(
        "crm.tag", [["name", "=ilike", "SKUBUS"]], ["name"], limit=10,
    )
    urgent_ids = {int(item["id"]) for item in urgent_tags}

    raw_moves = reader.search_read(
        "stock.move", [["raw_material_production_id", "in", production_ids]],
        ["raw_material_production_id", "state"], limit=10000,
    ) if production_ids else []
    raw_move_states_by_production: dict[int, list[str]] = {}
    for move in raw_moves:
        production_id = _relation_id(move.get("raw_material_production_id"))
        if production_id is not None:
            raw_move_states_by_production.setdefault(production_id, []).append(
                str(move.get("state") or "")
            )

    aggregates: dict[str, dict[str, Any]] = {}
    excluded = 0
    for workorder in workorders:
        production = production_by_id.get(_relation_id(workorder.get("production_id")) or -1)
        origin = str(production.get("origin") or "").strip() if production else ""
        sale = sales_by_name.get(origin)
        if not sale:
            excluded += 1
            continue
        item = aggregates.setdefault(origin, {"hours": 0.0, "mo_ids": set(), "sale": sale})
        item["hours"] += float(workorder.get("duration_expected") or 0.0) / 60.0
        item["mo_ids"].add(int(production["id"]))

    candidates = []
    for so_name, values in aggregates.items():
        blockers: list[str] = []
        mo_ids = values["mo_ids"]
        missing_mo_reservations = [
            production_id for production_id in mo_ids
            if not raw_move_states_by_production.get(production_id)
            or any(
                state not in {"assigned", "done", "cancel"}
                for state in raw_move_states_by_production.get(production_id, [])
            )
        ]
        if missing_mo_reservations:
            blockers.append(f"MO komponentai nerezervuoti: {len(missing_mo_reservations)} MO")
        candidates.append(AssemblyCandidate(
            so_reference=so_name,
            delivery_date=_parse_date(values["sale"].get("commitment_date")),
            urgent=bool(urgent_ids & set(values["sale"].get("tag_ids") or [])),
            assembly_hours=round(values["hours"], 2),
            manufacturing_order_count=len(mo_ids),
            system_ready=not blockers,
            system_blockers=tuple(blockers),
        ))
    candidates.sort(key=lambda item: (item.delivery_date or date.max, not item.urgent, item.so_reference))
    from datetime import datetime, timezone
    return CandidateResult(
        candidates=tuple(candidates),
        read_at=datetime.now(timezone.utc).isoformat(),
        excluded_without_exact_so=excluded,
    )


def load_plan_execution(
    reader: OdooReader, so_references: list[str] | tuple[str, ...],
) -> tuple[PlanExecutionStatus, ...]:
    references = tuple(dict.fromkeys(str(value).strip() for value in so_references if value))
    if not references:
        return ()
    workcenters = reader.search_read(
        "mrp.workcenter", ["|", ["name", "ilike", "Assembly"], ["name", "ilike", "Surink"]],
        ["name"], limit=20,
    )
    workcenter_ids = [int(item["id"]) for item in workcenters]
    if len(workcenter_ids) != 1:
        raise ValueError(f"Tikėtasi vieno aktyvaus Assembly darbo centro, rasta: {len(workcenter_ids)}.")
    productions = reader.search_read(
        "mrp.production", [["origin", "in", list(references)]],
        ["origin"], limit=10000,
    )
    production_origin = {
        int(item["id"]): str(item.get("origin") or "").strip() for item in productions
    }
    workorders = reader.search_read(
        "mrp.workorder",
        [["production_id", "in", list(production_origin)], ["workcenter_id", "in", workcenter_ids]],
        ["production_id", "state", "date_start", "date_finished"], limit=10000,
    ) if production_origin else []
    states_by_so: dict[str, list[dict[str, Any]]] = {reference: [] for reference in references}
    for workorder in workorders:
        origin = production_origin.get(_relation_id(workorder.get("production_id")) or -1)
        if origin in states_by_so:
            states_by_so[origin].append(workorder)

    result: list[PlanExecutionStatus] = []
    for reference in references:
        rows = states_by_so[reference]
        completed = sum(str(row.get("state")) in {"done", "cancel"} for row in rows)
        if not rows:
            status, label = "unknown", "NĖRA DUOMENŲ"
        elif completed == len(rows):
            status, label = "completed", "UŽBAIGTA"
        elif any(str(row.get("state")) == "progress" for row in rows):
            status, label = "in_progress", "VYKDOMA"
        else:
            status, label = "not_started", "NEPRADĖTA"
        result.append(PlanExecutionStatus(
            so_reference=reference, status=status, label=label,
            assembly_workorders=len(rows), completed_workorders=completed,
        ))
    return tuple(result)
