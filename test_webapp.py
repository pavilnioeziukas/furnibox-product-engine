from __future__ import annotations

import importlib
import io


def load_webapp(monkeypatch, tmp_path):
    monkeypatch.setenv("FURNIBOX_WEB_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("FURNIBOX_WEB_SECRET", "test-secret")
    monkeypatch.delenv("FURNIBOX_WEB_PASSWORD", raising=False)

    import webapp.app as webapp

    return importlib.reload(webapp)


def test_health_and_index(monkeypatch, tmp_path):
    webapp = load_webapp(monkeypatch, tmp_path)
    client = webapp.app.test_client()

    assert client.get("/health").get_json() == {"status": "ok"}
    assert client.get("/").status_code == 200


def test_upload_accepts_xlsx_and_rejects_other_files(monkeypatch, tmp_path):
    webapp = load_webapp(monkeypatch, tmp_path)
    client = webapp.app.test_client()

    accepted = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"xlsx"), "Reform BOM.xlsx")},
        content_type="multipart/form-data",
    )
    rejected = client.post(
        "/upload",
        data={"file": (io.BytesIO(b"csv"), "Reform BOM.csv")},
        content_type="multipart/form-data",
    )

    assert accepted.status_code == 302
    assert rejected.status_code == 400


def test_release_without_dataset_does_not_lock_queue(monkeypatch, tmp_path):
    webapp = load_webapp(monkeypatch, tmp_path)
    job_id = "missingdataset"
    job_dir = webapp.RUN_DIR / job_id
    job_dir.mkdir()
    webapp.write_job(
        job_dir,
        {
            "id": job_id,
            "action": "release_files",
            "title": "Generuoti BOM importo failus",
            "status": "QUEUED",
            "created_at": webapp.utc_now(),
            "upload": None,
            "files": [],
        },
    )
    webapp._reserved_jobs.add(job_id)

    webapp.run_job(job_id, "release_files", None)

    assert webapp.read_job(job_dir)["status"] == "ERROR"
    assert job_id not in webapp._reserved_jobs
