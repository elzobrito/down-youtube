"""FastAPI job routes (TestClient)."""

import pytest
from fastapi.testclient import TestClient

from app import jobs as jobs_mod
from app.jobs import set_process_function
from config import Config
from database import init_database


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db = tmp_path / "api.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()
    set_process_function(lambda job: {"status": "done", "expanded_count": 1, "result_transcription_id": 1})
    jobs_mod.stop_worker_loop(timeout=1.0)

    # Clear any token for open local tests
    monkeypatch.delenv("DOWN_YOUTUBE_API_TOKEN", raising=False)

    from api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    jobs_mod.stop_worker_loop(timeout=1.0)
    set_process_function(None)


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_get_job(client):
    r = client.post("/v1/jobs", json={"url": "https://example.com/video"})
    assert r.status_code == 202
    jid = r.json()["job_id"]
    assert jid

    # poll (worker loop idles ~0.3s when empty)
    import time

    body = None
    for _ in range(40):
        g = client.get(f"/v1/jobs/{jid}")
        assert g.status_code == 200
        body = g.json()
        if body["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.1)
    assert body is not None
    assert body["status"] == "done", body
    assert body["input_type"] == "url"


def test_list_jobs(client):
    client.post("/v1/jobs", json={"url": "https://example.com/a"})
    r = client.get("/v1/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json()


def test_job_results_list_exposed_for_batch(tmp_path, monkeypatch):
    """API exposes ordered results list without breaking singular fields."""
    db = tmp_path / "api-batch.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()

    def process(job):
        return {
            "status": "done",
            "expanded_count": 2,
            "results": [
                {"transcription_id": 1, "video_id": 10},
                {"transcription_id": 2, "video_id": 20},
            ],
        }

    set_process_function(process)
    jobs_mod.stop_worker_loop(timeout=1.0)
    monkeypatch.delenv("DOWN_YOUTUBE_API_TOKEN", raising=False)

    from app.jobs import create_batch_job, wait_job
    from api.main import create_app

    jid = create_batch_job(
        ["https://example.com/1", "https://example.com/2"],
        auto_start=True,
    )
    wait_job(jid, timeout=5)
    app = create_app()
    with TestClient(app) as c:
        r = c.get(f"/v1/jobs/{jid}")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "done"
        assert body["results"] == [
            {"transcription_id": 1, "video_id": 10},
            {"transcription_id": 2, "video_id": 20},
        ]
        # singular remains null for multi
        assert body.get("result_transcription_id") in (None, 0)

    jobs_mod.stop_worker_loop(timeout=1.0)
    set_process_function(None)
