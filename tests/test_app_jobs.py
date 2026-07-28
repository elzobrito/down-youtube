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


def test_job_freezes_asr_preprocess_snapshot(monkeypatch):
    from database import set_setting
    from app.jobs import create_batch_job

    set_setting("asr_audio_preprocess", "speech")
    jid = create_job(url="https://example.com/snap", auto_start=False)
    job = get_job(jid)
    assert job.options is not None
    assert job.options.get("asr_audio_preprocess") == "speech"

    # Changing settings after create must not alter the frozen snapshot
    set_setting("asr_audio_preprocess", "light")
    job2 = get_job(jid)
    assert job2.options.get("asr_audio_preprocess") == "speech"

    batch_id = create_batch_job(
        ["https://example.com/a", "https://example.com/b"],
        auto_start=False,
    )
    batch = get_job(batch_id)
    assert batch.options.get("asr_audio_preprocess") == "light"


def test_legacy_job_without_options_defaults_off():
    from database import insert_job

    insert_job("legacy-no-opts", "url", "https://example.com/legacy", status="queued")
    job = get_job("legacy-no-opts")
    assert job.options == {"asr_audio_preprocess": "off"}


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


def test_orphan_running_failed_on_startup_then_queued_runs():
    """Restart recovery: orphan running → failed; next queued processes."""
    from app.jobs import get_job, reconcile_jobs_on_startup, start_worker_loop, wait_job
    from database import insert_job, update_job_fields

    orphan = "orphan-running-1"
    insert_job(orphan, "url", "https://example.com/orphan", status="queued")
    update_job_fields(orphan, status="running")

    next_id = create_job(url="https://example.com/next", auto_start=False)
    seen = []

    def process(job):
        seen.append(job.id)
        return {"status": "done", "expanded_count": 1, "result_transcription_id": 7}

    set_process_function(process)
    failed = reconcile_jobs_on_startup()
    assert orphan in failed
    assert get_job(orphan).status == "failed"
    assert "interrupt" in (get_job(orphan).error_message or "").lower() or "restart" in (
        get_job(orphan).error_message or ""
    ).lower()

    start_worker_loop()
    job = wait_job(next_id, timeout=5.0)
    assert job.status == "done"
    assert next_id in seen
    assert orphan not in seen


def test_claim_queued_is_atomic():
    from database import claim_next_queued_job, get_job_row, insert_job

    insert_job("j-atomic-1", "url", "https://example.com/a", status="queued")
    a = claim_next_queued_job(worker_id="worker-a")
    b = claim_next_queued_job(worker_id="worker-b")
    assert a == "j-atomic-1"
    assert b is None
    row = get_job_row("j-atomic-1")
    assert row[14] == "worker-a"
    assert row[15] is not None


def test_fresh_job_lease_survives_second_startup():
    from app.jobs import get_job, reconcile_jobs_on_startup
    from database import claim_next_queued_job, insert_job

    insert_job("live-job", "url", "https://example.com/live", status="queued")
    assert claim_next_queued_job(worker_id="worker-a") == "live-job"
    assert reconcile_jobs_on_startup(stale_after_seconds=60) == []
    assert get_job("live-job").status == "running"


def test_expired_job_lease_is_recovered():
    from datetime import datetime, timedelta

    from app.jobs import get_job, reconcile_jobs_on_startup
    from database import claim_next_queued_job, insert_job, update_job_fields

    insert_job("stale-job", "url", "https://example.com/stale", status="queued")
    assert claim_next_queued_job(worker_id="worker-old") == "stale-job"
    update_job_fields(
        "stale-job",
        heartbeat_at=datetime.now() - timedelta(seconds=300),
    )
    failed = reconcile_jobs_on_startup(stale_after_seconds=60)
    assert failed == ["stale-job"]
    assert get_job("stale-job").status == "failed"


def test_heartbeat_update_is_owner_scoped():
    from database import (
        claim_next_queued_job,
        get_job_row,
        insert_job,
        touch_job_heartbeat,
    )

    insert_job("owned-job", "url", "https://example.com/owned", status="queued")
    assert claim_next_queued_job(worker_id="worker-a") == "owned-job"
    before = get_job_row("owned-job")[15]
    assert touch_job_heartbeat("owned-job", "worker-b") is False
    assert get_job_row("owned-job")[15] == before
    assert touch_job_heartbeat("owned-job", "worker-a") is True
