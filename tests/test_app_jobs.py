"""Unit tests for app.jobs store and queue (no network)."""

import time
from pathlib import Path

import pytest

from app import jobs as jobs_mod
from app.jobs import cancel_job, create_job, get_job, list_jobs, set_process_function, wait_job
from database import init_database
from config import Config


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Point app DB at a temp file for each test."""
    db = tmp_path / "test.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    # Reset Config singleton paths if re-read
    Config._instance = cfg
    init_database()
    set_process_function(None)
    jobs_mod.stop_worker_loop(timeout=1.0)
    yield
    jobs_mod.stop_worker_loop(timeout=1.0)
    set_process_function(None)


def test_create_and_get_job_queued_then_done():
    def fake_process(job):
        time.sleep(0.05)
        return {"status": "done", "expanded_count": 1, "result_transcription_id": 42}

    set_process_function(fake_process)
    jid = create_job(url="https://example.com/v/1", auto_start=True)
    job = wait_job(jid, timeout=5.0)
    assert job.status == "done"
    assert job.input_type == "url"
    assert job.result_transcription_id == 42
    assert "Job started" in (job.log_tail or "") or job.log_tail is not None


def test_cancel_queued_job():
    set_process_function(lambda job: time.sleep(10) or {"status": "done"})
    # Create without starting so it stays queued
    jid = create_job(url="https://example.com/a", auto_start=False)
    assert get_job(jid).status == "queued"
    assert cancel_job(jid) is True
    assert get_job(jid).status == "cancelled"


def test_list_jobs_filter():
    set_process_function(lambda job: {"status": "done"})
    j1 = create_job(url="https://example.com/1", auto_start=True)
    wait_job(j1, timeout=5)
    j2 = create_job(path="/tmp/x.mp3", auto_start=False)
    done = list_jobs(status="done")
    queued = list_jobs(status="queued")
    assert any(j.id == j1 for j in done)
    assert any(j.id == j2 for j in queued)


def test_create_requires_url_or_path():
    with pytest.raises(ValueError):
        create_job()
    with pytest.raises(ValueError):
        create_job(url="http://a", path="/tmp/b")


def test_update_progress_merges_by_stage():
    from app.jobs import create_job, get_job, update_progress

    set_process_function(lambda job: time.sleep(0.2) or {"status": "done"})
    jid = create_job(url="https://example.com/p", auto_start=False)
    update_progress(jid, {"stage": "download", "percent": 40, "speed": "1M"})
    update_progress(jid, {"stage": "transcription", "percent": 10})
    update_progress(jid, {"stage": "download", "percent": 100})
    job = get_job(jid)
    assert job.progress is not None
    by = job.progress.get("by_stage") or {}
    assert by["download"]["percent"] == 100
    assert by["transcription"]["percent"] == 10
