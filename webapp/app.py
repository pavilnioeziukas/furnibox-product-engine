from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
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


STATE_DIR = Path(
    os.getenv(
        "FURNIBOX_WEB_STATE_DIR",
        BASE_DIR / "web_state",
    )
).resolve()

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

MAX_UPLOAD_BYTES = (
    int(
        os.getenv(
            "FURNIBOX_MAX_UPLOAD_MB",
            "100",
        )
    )
    * 1024
    * 1024
)


app = Flask(__name__)

app.secret_key = os.getenv(
    "FURNIBOX_WEB_SECRET",
    secrets.token_hex(32),
)

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


ACTIONS: dict[str, dict[str, Any]] = {
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
    return bool(
        os.getenv(
            "FURNIBOX_WEB_PASSWORD",
            "",
        ).strip()
    )


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

    if not session.get("authenticated"):
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
        expected = os.getenv(
            "FURNIBOX_WEB_PASSWORD",
            "",
        )

        if secrets.compare_digest(
            request.form.get(
                "password",
                "",
            ),
            expected,
        ):
            session["authenticated"] = True

            return redirect(
                request.args.get("next")
                or url_for("index")
            )

        error = "Neteisingas slaptažodis."

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
    shared_roots = {
        Path(
            os.getenv(
                "FURNIBOX_SHARED_DATA",
                STATE_DIR / "shared_data",
            )
        ),
        Path(
            os.getenv(
                "FURNIBOX_SHARED_DATA_DIR",
                STATE_DIR / "shared_data",
            )
        ),
    }

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

    roots.extend(
        [
            Path(
                os.getenv(
                    "FURNIBOX_SHARED_DATA",
                    STATE_DIR
                    / "shared_data",
                )
            ),
            Path(
                os.getenv(
                    "FURNIBOX_SHARED_DATA_DIR",
                    STATE_DIR
                    / "shared_data",
                )
            ),
        ]
    )

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

    env[
        "FURNIBOX_ENVIRONMENT"
    ] = "PRODUCTION"

    env[
        "PYTHONUTF8"
    ] = "1"

    shared_data = str(
        STATE_DIR
        / "shared_data"
    )

    env.setdefault(
        "FURNIBOX_SHARED_DATA",
        shared_data,
    )

    env.setdefault(
        "FURNIBOX_SHARED_DATA_DIR",
        shared_data,
    )

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

        files = collect_outputs(
            before,
            output_dir,
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

        job.update(
            status=(
                "PASS"
                if return_code == 0
                else "FAIL"
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