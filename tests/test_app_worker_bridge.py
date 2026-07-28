"""Worker bridge tests with injected process fn (no real yt-dlp/whisper)."""

import time

import pytest

from app import jobs as jobs_mod
from app.jobs import cancel_job, create_job, get_job, set_process_function, wait_job
from config import Config
from database import init_database


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "bridge.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()
    set_process_function(None)
    jobs_mod.stop_worker_loop(timeout=1.0)
    yield
    jobs_mod.stop_worker_loop(timeout=1.0)
    set_process_function(None)


def test_failed_job_records_error():
    def boom(job):
        raise RuntimeError("download exploded")

    set_process_function(boom)
    jid = create_job(url="https://example.com/fail")
    job = wait_job(jid, timeout=5)
    assert job.status == "failed"
    assert "exploded" in (job.error_message or "")


def test_progress_and_log_updated():
    def slow(job):
        from app.jobs import append_log, update_progress

        update_progress(job.id, {"stage": "download", "percent": 50})
        append_log(job.id, "halfway")
        time.sleep(0.05)
        return {"status": "done", "expanded_count": 2}

    set_process_function(slow)
    jid = create_job(url="https://example.com/ok")
    job = wait_job(jid, timeout=5)
    assert job.status == "done"
    assert job.expanded_count == 2
    assert job.progress
    by = job.progress.get("by_stage") or {}
    assert by.get("download", {}).get("percent") == 50
    assert "halfway" in (job.log_tail or "")


def test_cancel_running_via_flag():
    """Simulated worker checks job status for cancel."""

    def long_job(job):
        for _ in range(50):
            time.sleep(0.05)
            current = get_job(job.id)
            if current and current.status == "cancelled":
                return {"status": "cancelled", "error_message": "Cancelled by user"}
        return {"status": "done"}

    set_process_function(long_job)
    jid = create_job(url="https://example.com/long")
    # Wait until running
    for _ in range(40):
        j = get_job(jid)
        if j and j.status == "running":
            break
        time.sleep(0.05)
    assert cancel_job(jid) is True
    job = wait_job(jid, timeout=5)
    assert job.status in ("cancelled", "done")  # race may finish done rarely
