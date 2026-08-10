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

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.getenv("FURNIBOX_WEB_STATE_DIR", BASE_DIR / "web_state")).resolve()
UPLOAD_DIR = STATE_DIR / "uploads"
RUN_DIR = STATE_DIR / "runs"
MAX_UPLOAD_BYTES = int(os.getenv("FURNIBOX_MAX_UPLOAD_MB", "100")) * 1024 * 1024

app = Flask(__name__)
app.secret_key = os.getenv("FURNIBOX_WEB_SECRET", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

for directory in (UPLOAD_DIR, RUN_DIR):
    directory.mkdir(parents=True, exist_ok=True)


ACTIONS: dict[str, dict[str, Any]] = {
    "stock_by_location": {
        "title": "Generuoti SKU likučius pagal lokaciją",
        "description": "Nuskaito Production likučius WH/Stock ir C/Stock lokacijose bei paskutinius faktinius pirkimų gavimus.",
        "module": "run_stock_by_location",
        "requires_upload": False,
    },
    "so_supply_status": {
        "title": "Patikrinti SO tiekimo būklę",
        "description": "Pagal SO parodo, ar faktinis MO poreikis rezervuotas ir kur dabar yra Furnix detalės: PO, gavime, rūšiavime ar WH/Stock.",
        "script": "run_so_supply_status.py",
        "requires_upload": False,
        "requires_so_number": True,
        "args": ["--so-number", "{so_number}", "--output-dir", "{output_dir}"],
    },
    "odoo_snapshot": {
        "title": "Nuskaityti Odoo duomenis",
        "description": "Atnaujina tik skaitomą Odoo produktų, BOM ir kainų momentinę kopiją.",
        "script": "main.py",
        "requires_upload": False,
    },
    "odoo_map": {
        "title": "Generuoti Odoo MAP",
        "description": "Nuskaito aktyvius Odoo BOM ir sukuria Dataset generavimui reikalingą Odoo_MAP.xlsx.",
        "script": "odoo_map.py",
        "requires_upload": False,
    },
    "bom_operations_reference": {
        "title": "Generuoti BOM operacijų etaloną",
        "description": "Nuskaito Production BOM operacijas ir sukuria Validated Dataset reikalingą operacijų etaloną.",
        "script": "bom_operations_reference_v1.py",
        "requires_upload": False,
    },
    "purchase_prices": {
        "title": "Nuskaityti paskutines pirkimo kainas",
        "description": "Atnaujina komponentų paskutinių pirkimų kainų failą.",
        "script": "last_purchase_prices.py",
        "requires_upload": False,
    },
    "validated_dataset": {
        "title": "Generuoti Validated Dataset",
        "description": "Iš įkelto Reform BOM ir Production etalonų sukuria patikrintą duomenų rinkinį.",
        "script": "generate_full_validated_dataset.py",
        "requires_upload": True,
        "args": ["--bom-input", "{upload}"],
    },
    "product_import": {
        "title": "Paruošti produktų importo failą",
        "description": "Generuoja Odoo importui skirtą Excel; Odoo duomenų nekeičia.",
        "script": "product_import_v10.py",
        "requires_upload": True,
        "args": ["--bom-input", "{upload}"],
    },
    "release_analysis": {
        "title": "Analizuoti BOM release",
        "description": "Palygina naujausią Validated Dataset su Production ir parengia release planą.",
        "script": "analyze_bom_release.py",
        "requires_upload": False,
    },
    "acceptance": {
        "title": "Paleisti acceptance patikrą",
        "description": "Patikrina naujausią Validated Dataset ir pateikia PASS arba FAIL ataskaitą.",
        "script": "pre_activation_acceptance.py",
        "requires_upload": False,
        "args": ["--source", "dataset"],
    },
    "release_files": {
        "title": "Generuoti BOM importo failus",
        "description": "Generuoja Excel importo failus iš patvirtinto Dataset; Odoo duomenų nekeičia.",
        "script": "generate_bom_release.py",
        "requires_upload": False,
        "needs_dataset_arg": True,
    },
}

_jobs_lock = threading.Lock()
_active_processes: dict[str, subprocess.Popen[str]] = {}
_reserved_jobs: set[str] = set()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def auth_enabled() -> bool:
    return bool(os.getenv("FURNIBOX_WEB_PASSWORD", "").strip())


@app.before_request
def require_login():
    if request.endpoint in {"login", "health", "static"} or not auth_enabled():
        return None
    if not session.get("authenticated"):
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        expected = os.getenv("FURNIBOX_WEB_PASSWORD", "")
        if secrets.compare_digest(request.form.get("password", ""), expected):
            session["authenticated"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "Neteisingas slaptažodis."
    return render_template("login.html", error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def read_job(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / "job.json").read_text(encoding="utf-8"))


def write_job(job_dir: Path, payload: dict[str, Any]) -> None:
    tmp = job_dir / "job.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(job_dir / "job.json")


def list_jobs() -> list[dict[str, Any]]:
    jobs = []
    for job_dir in RUN_DIR.iterdir():
        if job_dir.is_dir() and (job_dir / "job.json").exists():
            try:
                jobs.append(read_job(job_dir))
            except (OSError, json.JSONDecodeError):
                continue
    return sorted(jobs, key=lambda item: item["created_at"], reverse=True)[:50]


def latest_upload() -> Path | None:
    files = [path for path in UPLOAD_DIR.glob("*.xlsx") if path.is_file()]
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def latest_dataset() -> Path | None:
    shared_roots = {
        Path(os.getenv("FURNIBOX_SHARED_DATA", STATE_DIR / "shared_data")),
        Path(os.getenv("FURNIBOX_SHARED_DATA_DIR", STATE_DIR / "shared_data")),
    }
    candidates: list[Path] = []
    for root in shared_roots:
        if root.exists():
            candidates.extend(root.glob("validated_datasets/**/*.json"))
    candidates = [path for path in candidates if "Validated_Product_Dataset" in path.name]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def snapshot_outputs() -> dict[str, int]:
    result: dict[str, int] = {}
    roots = [BASE_DIR / "output", BASE_DIR / "validated_datasets"]
    roots.extend([
        Path(os.getenv("FURNIBOX_SHARED_DATA", STATE_DIR / "shared_data")),
        Path(os.getenv("FURNIBOX_SHARED_DATA_DIR", STATE_DIR / "shared_data")),
    ])
    for root in roots:
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file():
                    result[str(path.resolve())] = path.stat().st_mtime_ns
    return result


def collect_outputs(before: dict[str, int], destination: Path) -> list[dict[str, str]]:
    files = []
    for absolute, mtime in snapshot_outputs().items():
        source = Path(absolute)
        if before.get(absolute) == mtime:
            continue
        target = destination / source.name
        counter = 2
        while target.exists():
            target = destination / f"{source.stem}_{counter}{source.suffix}"
            counter += 1
        shutil.copy2(source, target)
        files.append({"name": target.name, "path": str(target)})
    return sorted(files, key=lambda item: item["name"])


def run_job(
    job_id: str,
    action_key: str,
    upload: Path | None,
    so_number: str | None = None,
) -> None:
    job_dir = RUN_DIR / job_id
    output_dir = job_dir / "files"
    output_dir.mkdir(exist_ok=True)
    job = read_job(job_dir)
    action = ACTIONS[action_key]
    before = snapshot_outputs()
    if action.get("module"):
        command = [sys.executable, "-u", "-m", action["module"]]
    else:
        command = [sys.executable, "-u", str(BASE_DIR / action["script"])]
    for argument in action.get("args", []):
        command.append(argument.format(
            upload=str(upload) if upload else "",
            so_number=so_number or "",
            output_dir=str(output_dir),
        ))
    if action.get("needs_dataset_arg"):
        dataset = latest_dataset()
        if dataset is None:
            job.update(status="ERROR", finished_at=utc_now(), error="Validated Dataset dar nesukurtas.")
            write_job(job_dir, job)
            with _jobs_lock:
                _reserved_jobs.discard(job_id)
            return
        command.extend(["--dataset", str(dataset), "--output-dir", str(output_dir)])

    env = os.environ.copy()
    env["FURNIBOX_ENVIRONMENT"] = "PRODUCTION"
    env["PYTHONUTF8"] = "1"
    shared_data = str(STATE_DIR / "shared_data")
    env.setdefault("FURNIBOX_SHARED_DATA", shared_data)
    env.setdefault("FURNIBOX_SHARED_DATA_DIR", shared_data)
    log_path = job_dir / "run.log"
    job.update(status="RUNNING", started_at=utc_now())
    write_job(job_dir, job)
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            with _jobs_lock:
                _active_processes[job_id] = process
            return_code = process.wait()
        files = collect_outputs(before, output_dir)
        known_paths = {item["path"] for item in files}
        for path in sorted(output_dir.iterdir()):
            if path.is_file() and str(path) not in known_paths:
                files.append({"name": path.name, "path": str(path)})
        job.update(
            status="PASS" if return_code == 0 else "FAIL",
            return_code=return_code,
            finished_at=utc_now(),
            files=files,
        )
    except Exception as exc:
        job.update(status="ERROR", finished_at=utc_now(), error=str(exc))
    finally:
        with _jobs_lock:
            _active_processes.pop(job_id, None)
            _reserved_jobs.discard(job_id)
        write_job(job_dir, job)


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


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        abort(400, "Nepasirinktas failas.")
    filename = secure_filename(file.filename)
    if Path(filename).suffix.lower() != ".xlsx":
        abort(400, "Leidžiamas tik .xlsx failas.")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = UPLOAD_DIR / f"{timestamp}_{filename}"
    file.save(target)
    return redirect(url_for("index"))


@app.post("/run/<action_key>")
def start_job(action_key: str):
    action = ACTIONS.get(action_key)
    if action is None:
        abort(404)
    upload_path = latest_upload()
    if action["requires_upload"] and upload_path is None:
        abort(409, "Pirmiausia įkelkite Reform BOM .xlsx failą.")
    so_number = request.form.get("so_number", "").strip().upper()
    if action.get("requires_so_number") and not so_number:
        abort(400, "Įveskite SO numerį.")
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        if _reserved_jobs:
            abort(409, "Kitas veiksmas jau vykdomas. Palaukite, kol jis baigsis.")
        _reserved_jobs.add(job_id)
    job_dir = RUN_DIR / job_id
    job_dir.mkdir()
    write_job(job_dir, {
        "id": job_id,
        "action": action_key,
        "title": action["title"],
        "status": "QUEUED",
        "created_at": utc_now(),
        "upload": upload_path.name if upload_path else None,
        "so_number": so_number or None,
        "files": [],
    })
    threading.Thread(
        target=run_job,
        args=(job_id, action_key, upload_path, so_number or None),
        daemon=True,
    ).start()
    return redirect(url_for("job_detail", job_id=job_id))


@app.get("/jobs/<job_id>")
def job_detail(job_id: str):
    job_dir = RUN_DIR / secure_filename(job_id)
    if not (job_dir / "job.json").exists():
        abort(404)
    job = read_job(job_dir)
    log = (job_dir / "run.log").read_text(encoding="utf-8", errors="replace") if (job_dir / "run.log").exists() else ""
    return render_template("job.html", job=job, log=log)


@app.get("/api/jobs/<job_id>")
def job_api(job_id: str):
    job_dir = RUN_DIR / secure_filename(job_id)
    if not (job_dir / "job.json").exists():
        abort(404)
    job = read_job(job_dir)
    log_path = job_dir / "run.log"
    job["log"] = log_path.read_text(encoding="utf-8", errors="replace")[-30000:] if log_path.exists() else ""
    return jsonify(job)


@app.post("/jobs/<job_id>/stop")
def stop_job(job_id: str):
    with _jobs_lock:
        process = _active_processes.get(job_id)
    if process and process.poll() is None:
        process.terminate()
    return redirect(url_for("job_detail", job_id=job_id))


@app.get("/jobs/<job_id>/files/<filename>")
def download(job_id: str, filename: str):
    path = RUN_DIR / secure_filename(job_id) / "files" / secure_filename(filename)
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


@app.get("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=False)