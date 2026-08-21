from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from so_pricing_rules import load_config, migrate_legacy_workbook, save_config
from cabinet_parts_price_parameters import (
    load_parameters as load_cabinet_parts_parameters,
    save_parameters as save_cabinet_parts_parameters,
    validate_parameters as validate_cabinet_parts_parameters,
)
from purchase_price_adjustments import (
    load_adjustments as load_purchase_price_adjustments,
    save_adjustments as save_purchase_price_adjustments,
    validate_adjustment as validate_purchase_price_adjustment,
)
from purchase_price_adjustments_import import (
    build_adjustment_preview,
    load_purchase_price_excel_adjustments,
    summarize_preview,
)
from webapp.product_engine import ProductEngineSettings, load_actions
from webapp.toc_foundation import READINESS_BLOCKER_REASONS, TocStore
from webapp.toc_odoo import ReadOnlyOdooReader, load_assembly_candidates
from webapp.toc_schedule import PRIORITY_RULE_VERSION, generate_daily_plan, serialize_plan


SETTINGS = ProductEngineSettings.from_env(BASE_DIR)
STATE_DIR = SETTINGS.state_dir

UPLOAD_DIR = STATE_DIR / "uploads"
RUN_DIR = STATE_DIR / "runs"

PRODUCTION_DATASET_DIR = (
    STATE_DIR
    / "shared_data"
    / "validated_datasets"
    / "production"
)
PRODUCTION_DATASET_PATH = (
    PRODUCTION_DATASET_DIR
    / "latest.json"
)

SO_PRICING_CONFIG_PATH = (
    STATE_DIR
    / "shared_data"
    / "so_pricing_rules.json"
)

CABINET_PARTS_PARAMETERS_PATH = (
    STATE_DIR
    / "shared_data"
    / "cabinet_parts_price_parameters.json"
)

PURCHASE_PRICE_ADJUSTMENTS_PATH = (
    STATE_DIR
    / "shared_data"
    / "purchase_price_adjustments.json"
)
LEGACY_PURCHASE_PRICE_ADJUSTMENTS_PATH = (
    STATE_DIR
    / "shared_data"
    / "tamara_adjustments.json"
)
PURCHASE_PRICE_IMPORT_DIR = (
    STATE_DIR
    / "purchase_price_imports"
)

DEFAULT_SO_PRICING_CONFIG_PATH = (
    BASE_DIR
    / "manifest"
    / "so_pricing_rules.json"
)

MAX_UPLOAD_BYTES = SETTINGS.max_upload_mb * 1024 * 1024


app = Flask(__name__)

app.secret_key = SETTINGS.web_secret or secrets.token_hex(32)

app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


for directory in (
    UPLOAD_DIR,
    RUN_DIR,
    PRODUCTION_DATASET_DIR,
    PURCHASE_PRICE_IMPORT_DIR,
):
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


TOC_STORE = TocStore(SETTINGS.database_url)
TOC_STORE.create_schema()
TOC_STORE.bootstrap_admin(
    SETTINGS.initial_admin_username,
    SETTINGS.initial_admin_password,
)


if (
    not PURCHASE_PRICE_ADJUSTMENTS_PATH.exists()
    and LEGACY_PURCHASE_PRICE_ADJUSTMENTS_PATH.exists()
):
    PURCHASE_PRICE_ADJUSTMENTS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        LEGACY_PURCHASE_PRICE_ADJUSTMENTS_PATH,
        PURCHASE_PRICE_ADJUSTMENTS_PATH,
    )


if (
    not SO_PRICING_CONFIG_PATH.exists()
    and DEFAULT_SO_PRICING_CONFIG_PATH.exists()
):
    SO_PRICING_CONFIG_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        DEFAULT_SO_PRICING_CONFIG_PATH,
        SO_PRICING_CONFIG_PATH,
    )


BUILTIN_ACTIONS: dict[str, dict[str, Any]] = {
    "mo_component_consumption_audit": {
        "title": "Audituoti užbaigtų MO komponentų sunaudojimą",
        "description": (
            "Tik skaitymo būdu randa užbaigtus MO, kuriuose faktiškai "
            "sunaudota mažiau komponentų negu buvo suplanuota pagal MO BOM. "
            "Parodo planuotą, sunaudotą ir trūkstamą kiekį."
        ),
        "script": "run_mo_component_consumption_audit.py",
        "requires_upload": False,
        "collect_changed_outputs": False,
        "args": ["--output-dir", "{output_dir}", "--days", "550"],
    },
    "odoo_supply_chain_audit": {
        "title": "Audituoti Odoo tiekimo grandines",
        "description": (
            "Tik skaitymo būdu atskiria galiojančius WH/INT pagal WH/INPC "
            "būseną, randa aktyvius MO su Invoiced SO ir patikrina "
            "WH/Input-Custom likučius. Odoo duomenų nekeičia."
        ),
        "script": "run_odoo_supply_chain_audit.py",
        "requires_upload": False,
        "collect_changed_outputs": False,
        "args": [
            "--output-dir",
            "{output_dir}",
        ],
    },
    "stock_by_location": {
        "title": "Generuoti SKU likučius pagal lokaciją",
        "description": (
            "Nuskaito Production likučius WH/Stock ir C/Stock "
            "lokacijose bei paskutinius faktinius pirkimų gavimus."
        ),
        "module": "run_stock_by_location",
        "requires_upload": False,
    },
    "so_supply_status": {
        "title": "Patikrinti SO tiekimo būklę",
        "description": (
            "Pagal SO parodo, ar faktinis MO poreikis rezervuotas "
            "ir kur dabar yra Furnix detalės: PO, gavime, "
            "rūšiavime ar WH/Stock."
        ),
        "script": "run_so_supply_status.py",
        "requires_upload": False,
        "requires_so_number": True,
        "args": [
            "--so-number",
            "{so_number}",
            "--output-dir",
            "{output_dir}",
        ],
    },
    "odoo_snapshot": {
        "title": "Nuskaityti Odoo duomenis",
        "description": (
            "Atnaujina tik skaitomą Odoo produktų, BOM ir "
            "kainų momentinę kopiją."
        ),
        "script": "main.py",
        "requires_upload": False,
    },
    "odoo_map": {
        "title": "Generuoti Odoo MAP",
        "description": (
            "Nuskaito aktyvius Odoo BOM ir sukuria Dataset "
            "generavimui reikalingą Odoo_MAP.xlsx."
        ),
        "script": "odoo_map.py",
        "requires_upload": False,
    },
    "bom_operations_reference": {
        "title": "Generuoti BOM operacijų etaloną",
        "description": (
            "Nuskaito Production BOM operacijas ir sukuria "
            "Validated Dataset reikalingą operacijų etaloną."
        ),
        "script": "bom_operations_reference_v1.py",
        "requires_upload": False,
    },
    "purchase_prices": {
        "title": "Nuskaityti paskutines pirkimo kainas",
        "description": (
            "Atnaujina komponentų paskutinių pirkimų kainų failą."
        ),
        "script": "last_purchase_prices.py",
        "requires_upload": False,
    },
    "refresh_reform_pricing": {
        "title": "Atnaujinti Reform kainodarą",
        "description": (
            "Vienu paleidimu atnaujina faktines ir Furnibox (Tamaros) pirkimo "
            "kainas, Cabinet Parts kainas, "
            "perskaičiuoja visą Reform BOM kainodarą ir pateikia galutinius "
            "failus tik tada, kai nėra BLOCKED pozicijų. Odoo nekeičia."
        ),
        "script": "refresh_reform_pricing.py",
        "requires_upload": True,
        "collect_changed_outputs": False,
        "blocked_return_codes": [2],
        "args": [
            "--bom-input",
            "{upload}",
            "--rules",
            str(SO_PRICING_CONFIG_PATH),
            "--output-dir",
            "{output_dir}",
        ],
    },
    "so_line_prices": {
        "title": "Generuoti Reform SO kainas",
        "description": (
            "Pagal aktualų Reform BOM, komponentų kainas ir "
            "aplikacijoje valdomas taisykles sukuria "
            "audituojamą SO kainoraštį."
        ),
        "script": "reform_so_line_prices.py",
        "requires_upload": True,
        "args": [
            "--bom-input",
            "{upload}",
            "--rules",
            str(SO_PRICING_CONFIG_PATH),
            "--price-input",
            str(
                BASE_DIR
                / "output"
                / "production"
                / "Reform_Final_Prices.xlsx"
            ),
            "--output-dir",
            "{output_dir}",
        ],
    },
    "validated_dataset": {
        "title": "Generuoti Validated Dataset",
        "description": (
            "Iš įkelto Reform BOM ir Production etalonų "
            "sukuria patikrintą duomenų rinkinį."
        ),
        "script": "generate_full_validated_dataset.py",
        "requires_upload": True,
        "args": [
            "--bom-input",
            "{upload}",
        ],
    },
    "product_import": {
        "title": "Paruošti produktų importo failą",
        "description": (
            "Generuoja Odoo importui skirtą Excel; "
            "Odoo duomenų nekeičia."
        ),
        "script": "product_import_v10.py",
        "requires_upload": True,
        "args": [
            "--bom-input",
            "{upload}",
        ],
    },
    "release_analysis": {
        "title": "Analizuoti BOM release",
        "description": (
            "Palygina naujausią Validated Dataset su Production "
            "ir parengia release planą."
        ),
        "script": "analyze_bom_release.py",
        "requires_upload": False,
    },
    "acceptance": {
        "title": "Paleisti acceptance patikrą",
        "description": (
            "Patikrina naujausią Validated Dataset ir pateikia "
            "PASS arba FAIL ataskaitą."
        ),
        "script": "pre_activation_acceptance.py",
        "requires_upload": False,
        "args": [
            "--source",
            "dataset",
        ],
    },
    "release_files": {
        "title": "Generuoti BOM importo failus",
        "description": (
            "Generuoja Excel importo failus iš patvirtinto Dataset; "
            "Odoo duomenų nekeičia."
        ),
        "script": "generate_bom_release.py",
        "requires_upload": False,
        "needs_dataset_arg": True,
    },
}

ACTIONS = load_actions(
    BUILTIN_ACTIONS,
    enabled_actions=SETTINGS.enabled_actions,
    action_modules=SETTINGS.action_modules,
)


_jobs_lock = threading.Lock()

_active_processes: dict[
    str,
    subprocess.Popen[str],
] = {}

_reserved_jobs: set[str] = set()


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def auth_enabled() -> bool:
    return TOC_STORE.has_users() or bool(SETTINGS.web_password)


@app.context_processor
def product_engine_context() -> dict[str, Any]:
    actor = TOC_STORE.get_user(session["actor_id"]) if session.get("actor_id") else None
    return {"product_engine": SETTINGS, "current_actor": actor}


@app.before_request
def require_login():
    if (
        request.endpoint
        in {
            "login",
            "health",
            "static",
        }
        or not auth_enabled()
    ):
        return None

    actor_id = session.get("actor_id")
    individual_actor = TOC_STORE.get_user(actor_id) if actor_id else None
    legacy_authenticated = session.get("authenticated") and not TOC_STORE.has_users()
    if not individual_actor and not legacy_authenticated:
        session.clear()
        return redirect(
            url_for(
                "login",
                next=request.path,
            )
        )

    return None


@app.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    error = None

    if request.method == "POST":
        actor = TOC_STORE.authenticate(
            request.form.get("username", ""),
            request.form.get("password", ""),
        )
        if actor:
            session.clear()
            session["actor_id"] = actor.id
            return redirect(request.args.get("next") or url_for("index"))

        expected = SETTINGS.web_password
        if (
            not TOC_STORE.has_users()
            and expected
            and secrets.compare_digest(request.form.get("password", ""), expected)
        ):
            session.clear()
            session["authenticated"] = True

            return redirect(
                request.args.get("next")
                or url_for("index")
            )

        error = "Neteisingas naudotojo vardas arba slaptažodis."

    return render_template(
        "login.html",
        error=error,
    )


@app.post("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("login")
    )


def require_toc_actor(*roles: str):
    actor_id = session.get("actor_id")
    actor = TOC_STORE.get_user(actor_id) if actor_id else None
    if not actor:
        abort(403, "Šiam veiksmui reikia individualios paskyros.")
    if roles and actor.role not in roles:
        abort(403, "Jūsų rolė neleidžia atlikti šio veiksmo.")
    return actor


def requested_business_date() -> date:
    raw = request.form.get("business_date", "")
    try:
        return date.fromisoformat(raw) if raw else date.today()
    except ValueError:
        abort(400, "Neteisinga darbo data.")


TOC_EVENT_LABELS = {
    "DailyAssemblyCapacityConfirmed": "Patvirtintas dienos pajėgumas",
    "ReadinessCheckStarted": "Pradėta rytinė READY patikra",
    "ReadinessConfirmed": "Užsakymas patvirtintas READY",
    "ReadinessBlockerOpened": "Užregistruota NOT READY priežastis",
    "ReadinessBlockerClosed": "Pašalinta NOT READY priežastis",
    "DailyPriorityPlanGenerated": "Sugeneruota dienos darbų eilė",
    "DailyPriorityPlanApproved": "Patvirtinta dienos darbų eilė",
}


def toc_event_description(item) -> str:
    payload = item.payload
    if item.event_type == "DailyAssemblyCapacityConfirmed":
        return f"{payload['employee_count']} darbuotojai · {payload['capacity_hours']} val."
    if item.event_type == "DailyPriorityPlanGenerated":
        today_count = sum(bool(entry.get("planned_today")) for entry in payload.get("entries", []))
        return f"{today_count} darbai šiandien · C {payload.get('capacity_hours', 0)} val."
    if item.event_type == "DailyPriorityPlanApproved":
        return "Patvirtinta sugeneruota plano versija"
    so_reference = payload.get("so_reference", "")
    reason = READINESS_BLOCKER_REASONS.get(payload.get("reason_code"), "")
    return " · ".join(value for value in (so_reference, reason, payload.get("comment", "")) if value)


@app.get("/toc/morning")
def toc_morning():
    require_toc_actor("production_manager", "administrator", "management")
    selected_raw = request.args.get("date", date.today().isoformat())
    try:
        selected_date = date.fromisoformat(selected_raw)
    except ValueError:
        abort(400, "Neteisinga darbo data.")
    events = TOC_STORE.list_events(selected_date)
    capacity_events = [item for item in events if item.event_type == "DailyAssemblyCapacityConfirmed"]
    plan_events = [item for item in events if item.event_type == "DailyPriorityPlanGenerated"]
    approval_events = [item for item in events if item.event_type == "DailyPriorityPlanApproved"]
    candidate_result = None
    candidate_error = None
    try:
        candidate_result = load_assembly_candidates(ReadOnlyOdooReader.from_env())
    except Exception as exc:
        candidate_error = str(exc)
    return render_template(
        "toc_morning.html", business_date=selected_date,
        events=list(reversed(events)),
        latest_capacity=capacity_events[-1] if capacity_events else None,
        readiness_reasons=READINESS_BLOCKER_REASONS,
        event_labels=TOC_EVENT_LABELS,
        event_description=toc_event_description,
        candidates=candidate_result.candidates if candidate_result else (),
        candidate_result=candidate_result,
        candidate_error=candidate_error,
        readiness_states=TOC_STORE.readiness_states(),
        latest_plan=plan_events[-1] if plan_events else None,
        approved_plan_ids={item.payload.get("plan_event_id") for item in approval_events},
    )


@app.post("/toc/morning/capacity")
def toc_confirm_capacity():
    actor = require_toc_actor("production_manager", "administrator")
    try:
        employee_count = int(request.form.get("employee_count", ""))
    except ValueError:
        abort(400, "Darbuotojų skaičius turi būti sveikasis skaičius.")
    if not 0 <= employee_count <= 30:
        abort(400, "Darbuotojų skaičius turi būti nuo 0 iki 30.")
    business_date = requested_business_date()
    TOC_STORE.append_event(
        event_type="DailyAssemblyCapacityConfirmed", business_date=business_date,
        actor_id=actor.id, rule_version="capacity-v1",
        payload={"employee_count": employee_count, "hours_per_employee": 8,
                 "capacity_hours": employee_count * 8},
    )
    flash(f"Patvirtintas dienos pajėgumas: {employee_count * 8} val.")
    return redirect(url_for("toc_morning", date=business_date.isoformat()))


@app.post("/toc/morning/start-check")
def toc_start_readiness_check():
    actor = require_toc_actor("production_manager", "administrator")
    business_date = requested_business_date()
    TOC_STORE.append_event(
        event_type="ReadinessCheckStarted", business_date=business_date,
        actor_id=actor.id, rule_version="readiness-v1", payload={},
    )
    flash("Rytinė READY patikra pradėta.")
    return redirect(url_for("toc_morning", date=business_date.isoformat()))


@app.post("/toc/morning/readiness")
def toc_record_readiness():
    actor = require_toc_actor("production_manager", "administrator")
    business_date = requested_business_date()
    ready = request.form.get("decision") == "ready"
    try:
        written = TOC_STORE.record_readiness(
            so_reference=request.form.get("so_reference", ""),
            business_date=business_date, actor_id=actor.id, ready=ready,
            reason_codes=request.form.getlist("reason_code"),
            comment=request.form.get("comment", ""),
        )
    except ValueError as exc:
        abort(400, str(exc))
    flash("Užsakymas pažymėtas READY." if ready else f"NOT READY priežastys užregistruotos: {len(written)}.")
    return redirect(url_for("toc_morning", date=business_date.isoformat()))


@app.post("/toc/morning/generate-plan")
def toc_generate_plan():
    actor = require_toc_actor("production_manager", "administrator")
    business_date = requested_business_date()
    events = TOC_STORE.list_events(business_date)
    capacities = [item for item in events if item.event_type == "DailyAssemblyCapacityConfirmed"]
    if not capacities:
        abort(400, "Prieš generuojant planą patvirtinkite dienos pajėgumą.")
    capacity = capacities[-1]
    try:
        source = load_assembly_candidates(ReadOnlyOdooReader.from_env())
    except Exception as exc:
        abort(503, f"Nepavyko nuskaityti Odoo kandidatų: {exc}")
    entries = generate_daily_plan(
        source.candidates, TOC_STORE.readiness_states(), business_date=business_date,
        capacity_hours=float(capacity.payload["capacity_hours"]),
    )
    TOC_STORE.append_event(
        event_type="DailyPriorityPlanGenerated", business_date=business_date,
        actor_id=actor.id, rule_version=PRIORITY_RULE_VERSION,
        payload={
            "source_read_at": source.read_at,
            "capacity_event_id": capacity.id,
            "capacity_hours": capacity.payload["capacity_hours"],
            "excluded_without_exact_so": source.excluded_without_exact_so,
            "entries": serialize_plan(entries),
        },
    )
    flash(f"Dienos eilė sugeneruota: {len(entries)} READY užsakymai.")
    return redirect(url_for("toc_morning", date=business_date.isoformat()))


@app.post("/toc/morning/approve-plan")
def toc_approve_plan():
    actor = require_toc_actor("production_manager", "administrator")
    business_date = requested_business_date()
    plan_event_id = request.form.get("plan_event_id", "")
    plan = TOC_STORE.get_event(plan_event_id)
    if not plan or plan.event_type != "DailyPriorityPlanGenerated" or plan.business_date != business_date:
        abort(400, "Nurodyta dienos plano versija neegzistuoja.")
    already_approved = any(
        item.event_type == "DailyPriorityPlanApproved"
        and item.payload.get("plan_event_id") == plan.id
        for item in TOC_STORE.list_events(business_date)
    )
    if already_approved:
        flash("Ši dienos plano versija jau patvirtinta.")
        return redirect(url_for("toc_morning", date=business_date.isoformat()))
    TOC_STORE.append_event(
        event_type="DailyPriorityPlanApproved", business_date=business_date,
        actor_id=actor.id, rule_version=plan.rule_version,
        payload={"plan_event_id": plan.id},
    )
    flash("Dienos darbų eilė patvirtinta.")
    return redirect(url_for("toc_morning", date=business_date.isoformat()))


def read_job(
    job_dir: Path,
) -> dict[str, Any]:
    return json.loads(
        (
            job_dir
            / "job.json"
        ).read_text(
            encoding="utf-8"
        )
    )


def write_job(
    job_dir: Path,
    payload: dict[str, Any],
) -> None:
    temporary = (
        job_dir
        / "job.json.tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        job_dir
        / "job.json"
    )


def list_jobs() -> list[dict[str, Any]]:
    jobs = []

    for job_dir in RUN_DIR.iterdir():
        if (
            job_dir.is_dir()
            and (
                job_dir
                / "job.json"
            ).exists()
        ):
            try:
                jobs.append(
                    read_job(job_dir)
                )
            except (
                OSError,
                json.JSONDecodeError,
            ):
                continue

    return sorted(
        jobs,
        key=lambda item: item["created_at"],
        reverse=True,
    )[:50]


def latest_upload() -> Path | None:
    files = [
        path
        for path in UPLOAD_DIR.glob("*.xlsx")
        if path.is_file()
    ]

    if not files:
        return None

    return max(
        files,
        key=lambda path: path.stat().st_mtime,
    )


def latest_dataset() -> Path | None:
    shared_roots = {SETTINGS.shared_data_dir}
    legacy_shared_data = os.getenv("FURNIBOX_SHARED_DATA", "").strip()
    if legacy_shared_data:
        shared_roots.add(Path(legacy_shared_data))

    candidates: list[Path] = []

    for root in shared_roots:
        if root.exists():
            candidates.extend(
                root.glob(
                    "validated_datasets/**/*.json"
                )
            )

    candidates = [
        path
        for path in candidates
        if (
            "Validated_Product_Dataset"
            in path.name
            or path.name == "latest.json"
        )
    ]

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda path: path.stat().st_mtime,
    )


def snapshot_outputs() -> dict[str, int]:
    result: dict[str, int] = {}

    roots = [
        BASE_DIR / "output",
        BASE_DIR / "validated_datasets",
    ]

    roots.append(SETTINGS.shared_data_dir)

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*"):
            if path.is_file():
                result[
                    str(path.resolve())
                ] = path.stat().st_mtime_ns

    return result


def collect_outputs(
    before: dict[str, int],
    destination: Path,
) -> list[dict[str, str]]:
    files = []

    for absolute, mtime in snapshot_outputs().items():
        source = Path(absolute)

        if before.get(absolute) == mtime:
            continue

        target = (
            destination
            / source.name
        )

        counter = 2

        while target.exists():
            target = (
                destination
                / (
                    f"{source.stem}_"
                    f"{counter}"
                    f"{source.suffix}"
                )
            )

            counter += 1

        shutil.copy2(
            source,
            target,
        )

        files.append(
            {
                "name": target.name,
                "path": str(target),
            }
        )

    return sorted(
        files,
        key=lambda item: item["name"],
    )


def run_job(
    job_id: str,
    action_key: str,
    upload: Path | None,
    so_number: str | None = None,
) -> None:
    job_dir = (
        RUN_DIR
        / job_id
    )

    output_dir = (
        job_dir
        / "files"
    )

    output_dir.mkdir(
        exist_ok=True
    )

    job = read_job(job_dir)

    action = ACTIONS[
        action_key
    ]

    before = snapshot_outputs()

    if action.get("module"):
        command = [
            sys.executable,
            "-u",
            "-m",
            action["module"],
        ]
    else:
        command = [
            sys.executable,
            "-u",
            str(
                BASE_DIR
                / action["script"]
            ),
        ]

    for argument in action.get(
        "args",
        [],
    ):
        command.append(
            argument.format(
                upload=(
                    str(upload)
                    if upload
                    else ""
                ),
                so_number=(
                    so_number
                    or ""
                ),
                output_dir=str(
                    output_dir
                ),
            )
        )

    if action.get(
        "needs_dataset_arg"
    ):
        dataset = latest_dataset()

        if dataset is None:
            job.update(
                status="ERROR",
                finished_at=utc_now(),
                error=(
                    "Validated Dataset "
                    "dar nesukurtas."
                ),
            )

            write_job(
                job_dir,
                job,
            )

            with _jobs_lock:
                _reserved_jobs.discard(
                    job_id
                )

            return

        command.extend(
            [
                "--dataset",
                str(dataset),
                "--output-dir",
                str(output_dir),
            ]
        )

    env = os.environ.copy()

    env["PRODUCT_ENGINE_ENVIRONMENT"] = SETTINGS.environment
    env["FURNIBOX_ENVIRONMENT"] = SETTINGS.environment

    env[
        "PYTHONUTF8"
    ] = "1"

    shared_data = str(
        STATE_DIR
        / "shared_data"
    )

    env.setdefault("PRODUCT_ENGINE_SHARED_DATA_DIR", shared_data)
    env.setdefault("FURNIBOX_SHARED_DATA", shared_data)
    env.setdefault("FURNIBOX_SHARED_DATA_DIR", shared_data)

    log_path = (
        job_dir
        / "run.log"
    )

    job.update(
        status="RUNNING",
        started_at=utc_now(),
    )

    write_job(
        job_dir,
        job,
    )

    try:
        with log_path.open(
            "w",
            encoding="utf-8",
        ) as log:
            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            with _jobs_lock:
                _active_processes[
                    job_id
                ] = process

            return_code = (
                process.wait()
            )

        files = (
            collect_outputs(before, output_dir)
            if action.get("collect_changed_outputs", True)
            else []
        )

        known_paths = {
            item["path"]
            for item in files
        }

        for path in sorted(
            output_dir.iterdir()
        ):
            if (
                path.is_file()
                and str(path)
                not in known_paths
            ):
                files.append(
                    {
                        "name": path.name,
                        "path": str(path),
                    }
                )

        blocked_return_codes = set(action.get("blocked_return_codes", []))
        job.update(
            status=(
                "PASS"
                if return_code == 0
                else (
                    "BLOCKED"
                    if return_code in blocked_return_codes
                    else "FAIL"
                )
            ),
            return_code=return_code,
            finished_at=utc_now(),
            files=files,
        )

    except Exception as exc:
        job.update(
            status="ERROR",
            finished_at=utc_now(),
            error=str(exc),
        )

    finally:
        with _jobs_lock:
            _active_processes.pop(
                job_id,
                None,
            )

            _reserved_jobs.discard(
                job_id
            )

        write_job(
            job_dir,
            job,
        )


@app.get("/")
def index():
    return render_template(
        "index.html",
        actions=ACTIONS,
        jobs=list_jobs(),
        upload=latest_upload(),
        dataset=latest_dataset(),
        auth_enabled=auth_enabled(),
        show_bom_workspace=SETTINGS.show_bom_workspace,
    )


@app.get("/purchase-pricing")
def purchase_pricing():
    parameters = (
        load_cabinet_parts_parameters(
            CABINET_PARTS_PARAMETERS_PATH
        )
    )

    purchase_price_adjustments = (
        load_purchase_price_adjustments(
            PURCHASE_PRICE_ADJUSTMENTS_PATH
        )
    )

    adjustment_query = request.args.get(
        "adjustment_q",
        "",
    ).strip()

    adjustment_rows = [
        {
            "sku": sku,
            **document,
        }
        for sku, document
        in purchase_price_adjustments.items()
    ]

    if adjustment_query:
        query = adjustment_query.casefold()

        adjustment_rows = [
            row
            for row in adjustment_rows
            if (
                query
                in row["sku"].casefold()
                or query
                in row["comment"].casefold()
            )
        ]

    return render_template(
        "purchase_pricing.html",
        parameters=parameters,
        adjustment_rows=adjustment_rows[:200],
        adjustment_total=len(
            purchase_price_adjustments
        ),
        adjustment_query=adjustment_query,
    )


@app.post("/purchase-pricing")
def update_purchase_pricing():
    document = {
        "back_rate_per_m2": form_number(
            "back_rate_per_m2"
        ),
        "processing_rate_per_m2": form_number(
            "processing_rate_per_m2"
        ),
        "ww_material_rate_per_m2": form_number(
            "ww_material_rate_per_m2"
        ),
        "bb_material_rate_per_m2": form_number(
            "bb_material_rate_per_m2"
        ),
        "no_material_rate_per_m2": form_number(
            "no_material_rate_per_m2"
        ),
        "small_part_threshold_m2": form_number(
            "small_part_threshold_m2"
        ),
        "small_part_surcharge": form_number(
            "small_part_surcharge"
        ),
        "furnix_markup_percent": form_number(
            "furnix_markup_percent"
        ),
        "output_decimals": request.form.get(
            "output_decimals",
            "",
        ).strip(),
    }

    try:
        parameters = (
            validate_cabinet_parts_parameters(
                document
            )
        )

        save_cabinet_parts_parameters(
            CABINET_PARTS_PARAMETERS_PATH,
            parameters,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    flash(
        "Pirkimo kainodaros parametrai išsaugoti."
    )

    return redirect(
        url_for(
            "purchase_pricing"
        )
    )


@app.post(
    "/purchase-pricing/adjustments/excel-preview"
)
def preview_purchase_price_excel():
    file = request.files.get("file")

    if file is None or not file.filename:
        abort(
            400,
            "Pasirinkite pirkimo kainų Excel failą.",
        )

    filename = secure_filename(file.filename)

    if Path(filename).suffix.lower() != ".xlsx":
        abort(
            400,
            "Leidžiamas tik .xlsx failas.",
        )

    import_id = uuid.uuid4().hex

    excel_path = (
        PURCHASE_PRICE_IMPORT_DIR
        / f"{import_id}.xlsx"
    )

    metadata_path = (
        PURCHASE_PRICE_IMPORT_DIR
        / f"{import_id}.json"
    )

    file.save(excel_path)

    try:
        excel_adjustments = (
            load_purchase_price_excel_adjustments(
                excel_path
            )
        )

        current_adjustments = (
            load_purchase_price_adjustments(
                PURCHASE_PRICE_ADJUSTMENTS_PATH
            )
        )

        preview_rows = build_adjustment_preview(
            excel_adjustments,
            current_adjustments,
        )

        summary = summarize_preview(
            preview_rows
        )

        changed_rows = [
            row
            for row in preview_rows
            if row.status != "SAME"
        ]

        metadata_path.write_text(
            json.dumps(
                {
                    "source_filename": filename,
                    "created_at": utc_now(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        return render_template(
            "purchase_price_adjustments_preview.html",
            import_id=import_id,
            source_filename=filename,
            summary=summary,
            rows=changed_rows[:500],
            changed_total=len(changed_rows),
        )

    except (ValueError, OSError) as exc:
        excel_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        abort(400, str(exc))


@app.post(
    "/purchase-pricing/adjustments/excel-apply/<import_id>"
)
def apply_purchase_price_excel(import_id: str):
    safe_import_id = secure_filename(import_id)

    if (
        not safe_import_id
        or safe_import_id != import_id
    ):
        abort(404)

    excel_path = (
        PURCHASE_PRICE_IMPORT_DIR
        / f"{import_id}.xlsx"
    )

    metadata_path = (
        PURCHASE_PRICE_IMPORT_DIR
        / f"{import_id}.json"
    )

    if (
        not excel_path.exists()
        or not metadata_path.exists()
    ):
        abort(
            404,
            "Excel peržiūra neberasta. Įkelkite failą iš naujo.",
        )

    try:
        metadata = json.loads(
            metadata_path.read_text(
                encoding="utf-8"
            )
        )

        excel_adjustments = (
            load_purchase_price_excel_adjustments(
                excel_path
            )
        )

        current_adjustments = (
            load_purchase_price_adjustments(
                PURCHASE_PRICE_ADJUSTMENTS_PATH
            )
        )

        preview_rows = build_adjustment_preview(
            excel_adjustments,
            current_adjustments,
        )

        rows_to_apply = [
            row
            for row in preview_rows
            if row.status in {
                "NEW",
                "CHANGED",
            }
        ]

        if not rows_to_apply:
            flash(
                "Pirkimo kainų Excel neturi naujų ar pakeistų kainų."
            )
            return redirect(
                url_for("purchase_pricing")
                + "#purchase-price-adjustments"
            )

        if PURCHASE_PRICE_ADJUSTMENTS_PATH.exists():
            backup_dir = (
                STATE_DIR
                / "shared_data"
                / "backups"
            )
            backup_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )

            backup_path = (
                backup_dir
                / f"purchase_price_adjustments_{timestamp}.json"
            )

            shutil.copy2(
                PURCHASE_PRICE_ADJUSTMENTS_PATH,
                backup_path,
            )

        source_filename = str(
            metadata.get(
                "source_filename",
                "Pirkimo kainų Excel",
            )
        )

        for row in rows_to_apply:
            current_adjustments[row.sku] = {
                "adjusted_purchase_price":
                    row.new_adjustment,
                "comment": (
                    "Imported from "
                    f"{source_filename}"
                ),
            }

        save_purchase_price_adjustments(
            PURCHASE_PRICE_ADJUSTMENTS_PATH,
            current_adjustments,
        )

        flash(
            f"Pritaikyta {len(rows_to_apply)} "
            "Pirkimo kainų pakeitimų."
        )

    except (
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        abort(400, str(exc))

    finally:
        excel_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)

    return redirect(
        url_for("purchase_pricing")
        + "#purchase-price-adjustments"
    )


@app.post(
    "/purchase-pricing/adjustments/<path:sku>"
)
def update_purchase_price_adjustment(
    sku: str,
):
    adjustments = (
        load_purchase_price_adjustments(
            PURCHASE_PRICE_ADJUSTMENTS_PATH
        )
    )

    if sku not in adjustments:
        abort(404)

    try:
        adjustments[sku] = (
            validate_purchase_price_adjustment(
                sku,
                {
                    "adjusted_purchase_price":
                        request.form.get(
                            "adjusted_purchase_price",
                            "",
                        ),
                    "comment":
                        request.form.get(
                            "comment",
                            "",
                        ),
                },
            )
        )

        save_purchase_price_adjustments(
            PURCHASE_PRICE_ADJUSTMENTS_PATH,
            adjustments,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    flash(
        f"Pirkimo kainos korekcija "
        f"{sku} išsaugota."
    )

    query = request.form.get(
        "return_query",
        "",
    ).strip()

    return redirect(
        url_for(
            "purchase_pricing",
            adjustment_q=query,
        )
        + "#purchase-price-adjustments"
    )


@app.get(
    "/purchase-pricing/adjustments/export"
)
def export_purchase_price_adjustments():
    if not PURCHASE_PRICE_ADJUSTMENTS_PATH.exists():
        abort(
            404,
            "Tamaros korekcijų saugykla dar nesukurta.",
        )

    return send_file(
        PURCHASE_PRICE_ADJUSTMENTS_PATH,
        as_attachment=True,
        download_name=(
            "purchase_price_adjustments.json"
        ),
    )


@app.post(
    "/purchase-pricing/adjustments/import"
)
def import_purchase_price_adjustments():
    file = request.files.get(
        "file"
    )

    if (
        file is None
        or not file.filename
    ):
        abort(
            400,
            "Pasirinkite Tamaros korekcijų JSON failą.",
        )

    filename = secure_filename(
        file.filename
    )

    if (
        Path(filename).suffix.lower()
        != ".json"
    ):
        abort(
            400,
            "Leidžiamas tik .json failas.",
        )

    temporary_path = (
        UPLOAD_DIR
        / (
            "purchase_price_adjustments_import_"
            f"{uuid.uuid4().hex}.json"
        )
    )

    file.save(
        temporary_path
    )

    try:
        adjustments = (
            load_purchase_price_adjustments(
                temporary_path
            )
        )

        if not adjustments:
            abort(
                400,
                (
                    "Importuojamas Tamaros korekcijų "
                    "failas neturi nė vienos korekcijos."
                ),
            )

        if PURCHASE_PRICE_ADJUSTMENTS_PATH.exists():
            backup_dir = (
                STATE_DIR
                / "shared_data"
                / "backups"
            )

            backup_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            timestamp = (
                datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )
            )

            backup_path = (
                backup_dir
                / (
                    "purchase_price_adjustments_"
                    f"{timestamp}.json"
                )
            )

            shutil.copy2(
                PURCHASE_PRICE_ADJUSTMENTS_PATH,
                backup_path,
            )

        save_purchase_price_adjustments(
            PURCHASE_PRICE_ADJUSTMENTS_PATH,
            adjustments,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    finally:
        temporary_path.unlink(
            missing_ok=True
        )

    flash(
        f"Importuotos {len(adjustments)} "
        "Tamaros pirkimo kainų korekcijos."
    )

    return redirect(
        url_for(
            "purchase_pricing"
        )
        + "#purchase-price-adjustments"
    )


@app.get("/pricing-rules")
def pricing_rules():
    document = load_config(
        SO_PRICING_CONFIG_PATH
    )

    query = request.args.get(
        "q",
        "",
    ).strip().casefold()

    assignments = document[
        "bom_skus"
    ]

    if query:
        assignments = [
            row
            for row in assignments
            if query
            in " ".join(
                str(value)
                for value
                in row.values()
            ).casefold()
        ]

    bom_counts = {}

    for row in document[
        "bom_skus"
    ]:
        category_id = row[
            "category_id"
        ]

        bom_counts[
            category_id
        ] = (
            bom_counts.get(
                category_id,
                0,
            )
            + 1
        )

    non_bom_counts = {}

    for row in document[
        "non_bom_skus"
    ]:
        category_id = row[
            "category_id"
        ]

        non_bom_counts[
            category_id
        ] = (
            non_bom_counts.get(
                category_id,
                0,
            )
            + 1
        )

    return render_template(
        "pricing_rules.html",
        config=document,
        assignments=assignments,
        bom_counts=bom_counts,
        non_bom_counts=non_bom_counts,
        configured=(
            SO_PRICING_CONFIG_PATH.exists()
        ),
        query=request.args.get(
            "q",
            "",
        ).strip(),
    )


@app.post(
    "/pricing-rules/migrate"
)
def migrate_pricing_rules():
    file = request.files.get(
        "file"
    )

    if (
        file is None
        or not file.filename
        or Path(
            secure_filename(
                file.filename
            )
        ).suffix.lower()
        != ".xlsx"
    ):
        abort(
            400,
            "Pasirinkite seną kainodaros .xlsx failą.",
        )

    temporary = (
        UPLOAD_DIR
        / (
            "pricing_migration_"
            f"{uuid.uuid4().hex}.xlsx"
        )
    )

    file.save(
        temporary
    )

    try:
        document = (
            migrate_legacy_workbook(
                temporary
            )
        )

        save_config(
            SO_PRICING_CONFIG_PATH,
            document,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    finally:
        temporary.unlink(
            missing_ok=True
        )

    flash(
        "Taisyklės perkeltos į aplikaciją. "
        "Seno Excel kasdieniam darbui nebereikia."
    )

    return redirect(
        url_for(
            "pricing_rules"
        )
    )


def form_number(
    name: str,
) -> float:
    raw = (
        request.form.get(
            name,
            "",
        )
        .strip()
        .replace(
            ",",
            ".",
        )
    )

    try:
        return float(raw)

    except ValueError:
        abort(
            400,
            (
                f"Laukas „{name}“ "
                "turi būti skaičius."
            ),
        )


@app.post(
    "/pricing-rules/adjustment"
)
def update_pricing_adjustment():
    document = load_config(
        SO_PRICING_CONFIG_PATH
    )

    document[
        "adjustment_rate"
    ] = (
        form_number(
            "adjustment_percent"
        )
        / 100
    )

    try:
        save_config(
            SO_PRICING_CONFIG_PATH,
            document,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    flash(
        "Bendra BOM kainodaros korekcija išsaugota."
    )

    return redirect(
        url_for(
            "pricing_rules"
        )
    )


@app.post(
    "/pricing-rules/categories/<category_id>"
)
def update_pricing_category(
    category_id: str,
):
    document = load_config(
        SO_PRICING_CONFIG_PATH
    )

    match = next(
        (
            row
            for row
            in document[
                "bom_categories"
            ]
            if row["id"]
            == category_id
        ),
        None,
    )

    if match is None:
        abort(404)

    for name in (
        "name",
        "source_category_id",
        "odoo_category",
    ):
        match[name] = (
            request.form.get(
                name,
                "",
            ).strip()
        )

    for name in (
        "assembly",
        "storage",
        "packaging",
        "put_on_pallet",
        "other",
        "markup",
    ):
        match[name] = (
            form_number(name)
        )

    save_config(
        SO_PRICING_CONFIG_PATH,
        document,
    )

    flash(
        f"BOM kategorija "
        f"{match['name']} išsaugota."
    )

    return redirect(
        url_for(
            "pricing_rules"
        )
        + "#bom-categories"
    )


@app.post(
    "/pricing-rules/bom-skus/<path:sku>"
)
def update_bom_sku(
    sku: str,
):
    document = load_config(
        SO_PRICING_CONFIG_PATH
    )

    match = next(
        (
            row
            for row
            in document[
                "bom_skus"
            ]
            if row[
                "sku"
            ].casefold()
            == sku.casefold()
        ),
        None,
    )

    if match is None:
        abort(404)

    match[
        "category_id"
    ] = request.form.get(
        "category_id",
        "",
    ).strip()

    try:
        save_config(
            SO_PRICING_CONFIG_PATH,
            document,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    flash(
        f"BOM SKU "
        f"{match['sku']} "
        "kategorija išsaugota."
    )

    return redirect(
        url_for(
            "pricing_rules",
            q=request.form.get(
                "return_query",
                "",
            ),
        )
        + "#bom-skus"
    )


@app.post(
    "/pricing-rules/non-bom-categories/<category_id>"
)
def update_non_bom_category(
    category_id: str,
):
    document = load_config(
        SO_PRICING_CONFIG_PATH
    )

    match = next(
        (
            row
            for row
            in document[
                "non_bom_categories"
            ]
            if row["id"]
            == category_id
        ),
        None,
    )

    if match is None:
        abort(404)

    match["name"] = (
        request.form.get(
            "name",
            "",
        ).strip()
    )

    for name in (
        "preparation",
        "storage",
        "bag",
        "sticker",
    ):
        match[name] = (
            form_number(name)
        )

    save_config(
        SO_PRICING_CONFIG_PATH,
        document,
    )

    flash(
        f"Ne BOM kategorija "
        f"{match['name']} išsaugota."
    )

    return redirect(
        url_for(
            "pricing_rules"
        )
        + "#non-bom-categories"
    )


@app.post(
    "/pricing-rules/non-bom-skus/<path:sku>"
)
def update_non_bom_sku(
    sku: str,
):
    document = load_config(
        SO_PRICING_CONFIG_PATH
    )

    match = next(
        (
            row
            for row
            in document[
                "non_bom_skus"
            ]
            if row[
                "sku"
            ].casefold()
            == sku.casefold()
        ),
        None,
    )

    if match is None:
        abort(404)

    match[
        "category_id"
    ] = request.form.get(
        "category_id",
        "",
    ).strip()

    try:
        save_config(
            SO_PRICING_CONFIG_PATH,
            document,
        )

    except ValueError as exc:
        abort(
            400,
            str(exc),
        )

    flash(
        f"Ne BOM SKU "
        f"{match['sku']} "
        "kategorija išsaugota."
    )

    return redirect(
        url_for(
            "pricing_rules"
        )
        + "#non-bom-skus"
    )


@app.post("/upload")
def upload():
    file = request.files.get(
        "file"
    )

    if (
        file is None
        or not file.filename
    ):
        abort(
            400,
            "Nepasirinktas failas.",
        )

    filename = secure_filename(
        file.filename
    )

    if (
        Path(filename).suffix.lower()
        != ".xlsx"
    ):
        abort(
            400,
            "Leidžiamas tik .xlsx failas.",
        )

    timestamp = (
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    target = (
        UPLOAD_DIR
        / (
            f"{timestamp}_"
            f"{filename}"
        )
    )

    file.save(
        target
    )

    return redirect(
        url_for("index")
    )


@app.post(
    "/upload/production-dataset"
)
def upload_production_dataset():
    """
    Store the active Production dataset in persistent web state.

    The validator resolves this exact path, so the original
    uploaded filename must not be used as the runtime filename.
    """

    file = request.files.get(
        "file"
    )

    if (
        file is None
        or not file.filename
    ):
        abort(
            400,
            "Nepasirinktas Validated Dataset JSON failas.",
        )

    if (
        Path(
            secure_filename(
                file.filename
            )
        ).suffix.lower()
        != ".json"
    ):
        abort(
            400,
            "Leidžiamas tik .json failas.",
        )

    payload = file.read()

    if not payload:
        abort(
            400,
            "Įkeltas failas tuščias.",
        )

    try:
        document = json.loads(
            payload
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        abort(
            400,
            "Failas nėra korektiškas JSON.",
        )

    if not isinstance(
        document,
        (
            dict,
            list,
        ),
    ):
        abort(
            400,
            (
                "Validated Dataset JSON "
                "šaknis turi būti objektas "
                "arba sąrašas."
            ),
        )

    PRODUCTION_DATASET_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        PRODUCTION_DATASET_PATH
        .with_suffix(
            ".json.tmp"
        )
    )

    temporary.write_bytes(
        payload
    )

    temporary.replace(
        PRODUCTION_DATASET_PATH
    )

    return redirect(
        url_for("index")
    )


@app.post(
    "/run/<action_key>"
)
def start_job(
    action_key: str,
):
    action = ACTIONS.get(
        action_key
    )

    if action is None:
        abort(404)

    upload_path = (
        latest_upload()
    )

    if (
        action[
            "requires_upload"
        ]
        and upload_path is None
    ):
        abort(
            409,
            (
                "Pirmiausia įkelkite "
                "Reform BOM .xlsx failą."
            ),
        )

    so_number = (
        request.form.get(
            "so_number",
            "",
        )
        .strip()
        .upper()
    )

    if (
        action.get(
            "requires_so_number"
        )
        and not so_number
    ):
        abort(
            400,
            "Įveskite SO numerį.",
        )

    job_id = (
        uuid.uuid4()
        .hex[:12]
    )

    with _jobs_lock:
        if _reserved_jobs:
            abort(
                409,
                (
                    "Kitas veiksmas jau vykdomas. "
                    "Palaukite, kol jis baigsis."
                ),
            )

        _reserved_jobs.add(
            job_id
        )

    job_dir = (
        RUN_DIR
        / job_id
    )

    job_dir.mkdir()

    write_job(
        job_dir,
        {
            "id": job_id,
            "action": action_key,
            "title": action["title"],
            "status": "QUEUED",
            "created_at": utc_now(),
            "upload": (
                upload_path.name
                if upload_path
                else None
            ),
            "so_number": (
                so_number
                or None
            ),
            "files": [],
        },
    )

    threading.Thread(
        target=run_job,
        args=(
            job_id,
            action_key,
            upload_path,
            so_number or None,
        ),
        daemon=True,
    ).start()

    return redirect(
        url_for(
            "job_detail",
            job_id=job_id,
        )
    )


@app.get(
    "/jobs/<job_id>"
)
def job_detail(
    job_id: str,
):
    job_dir = (
        RUN_DIR
        / secure_filename(
            job_id
        )
    )

    if not (
        job_dir
        / "job.json"
    ).exists():
        abort(404)

    job = read_job(
        job_dir
    )

    log_path = (
        job_dir
        / "run.log"
    )

    log = (
        log_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        if log_path.exists()
        else ""
    )

    return render_template(
        "job.html",
        job=job,
        log=log,
    )


@app.get(
    "/api/jobs/<job_id>"
)
def job_api(
    job_id: str,
):
    job_dir = (
        RUN_DIR
        / secure_filename(
            job_id
        )
    )

    if not (
        job_dir
        / "job.json"
    ).exists():
        abort(404)

    job = read_job(
        job_dir
    )

    log_path = (
        job_dir
        / "run.log"
    )

    job["log"] = (
        log_path.read_text(
            encoding="utf-8",
            errors="replace",
        )[-30000:]
        if log_path.exists()
        else ""
    )

    return jsonify(job)


@app.post(
    "/jobs/<job_id>/stop"
)
def stop_job(
    job_id: str,
):
    with _jobs_lock:
        process = (
            _active_processes.get(
                job_id
            )
        )

    if (
        process
        and process.poll()
        is None
    ):
        process.terminate()

    return redirect(
        url_for(
            "job_detail",
            job_id=job_id,
        )
    )


@app.get(
    "/jobs/<job_id>/files/<filename>"
)
def download(
    job_id: str,
    filename: str,
):
    path = (
        RUN_DIR
        / secure_filename(
            job_id
        )
        / "files"
        / secure_filename(
            filename
        )
    )

    if not path.is_file():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=path.name,
    )


@app.get("/health")
def health():
    return jsonify(
        status="ok"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "8080",
            )
        ),
        debug=False,
    )
