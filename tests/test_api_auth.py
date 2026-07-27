"""API token auth tests."""

import pytest
from fastapi.testclient import TestClient

from app import jobs as jobs_mod
from app.jobs import set_process_function
from config import Config
from database import init_database


@pytest.fixture()
def client_with_token(tmp_path, monkeypatch):
    db = tmp_path / "api-auth.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()
    set_process_function(lambda job: {"status": "done"})
    jobs_mod.stop_worker_loop(timeout=1.0)
    monkeypatch.setenv("DOWN_YOUTUBE_API_TOKEN", "secret-test-token")

    from api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    jobs_mod.stop_worker_loop(timeout=1.0)
    set_process_function(None)
    monkeypatch.delenv("DOWN_YOUTUBE_API_TOKEN", raising=False)


def test_health_open_without_token(client_with_token):
    # health is intentionally open
    r = client_with_token.get("/v1/health")
    assert r.status_code == 200


def test_jobs_require_token(client_with_token):
    r = client_with_token.post("/v1/jobs", json={"url": "https://example.com/z"})
    assert r.status_code == 401

    r2 = client_with_token.post(
        "/v1/jobs",
        json={"url": "https://example.com/z"},
        headers={"X-API-Key": "secret-test-token"},
    )
    assert r2.status_code == 202

    r3 = client_with_token.get(
        f"/v1/jobs/{r2.json()['job_id']}",
        headers={"Authorization": "Bearer secret-test-token"},
    )
    assert r3.status_code == 200
