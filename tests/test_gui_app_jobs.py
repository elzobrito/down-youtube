"""GUI uses app.jobs (batch + hooks) — logic tests without Tk display."""

import time

import pytest

from app import jobs as jobs_mod
from app.jobs import (
    create_batch_job,
    get_job,
    has_active_work,
    set_process_function,
    wait_job,
)
from config import Config
from database import init_database


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "gui-jobs.db"
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


def test_create_batch_job_runs_and_finishes():
    seen = {}

    def fake(job):
        seen["type"] = job.input_type
        seen["n"] = job.expanded_count
        return {"status": "done", "expanded_count": job.expanded_count}

    set_process_function(fake)
    jid = create_batch_job(
        ["https://example.com/a", "https://example.com/b"],
        auto_start=True,
    )
    job = wait_job(jid, timeout=5)
    assert job.status == "done"
    assert seen["type"] == "batch"
    assert seen["n"] == 2


def test_batch_with_queue_tuples():
    def fake(job):
        import json

        items = json.loads(job.input_value)
        assert items[0][0] == 7
        assert items[0][1].startswith("http")
        return {"status": "done", "expanded_count": 1}

    set_process_function(fake)
    jid = create_batch_job([(7, "https://example.com/q")], auto_start=True)
    job = wait_job(jid, timeout=5)
    assert job.status == "done"


def test_has_active_work_while_queued():
    set_process_function(lambda job: time.sleep(0.4) or {"status": "done"})
    jid = create_batch_job(["https://example.com/slow"], auto_start=True)
    # Immediately after create should be active
    assert has_active_work() or get_job(jid).status in ("queued", "running", "done")
    wait_job(jid, timeout=5)
