"""CLI jobs smoke tests."""

import pytest

from app import jobs as jobs_mod
from app.jobs import set_process_function
from cli.main import main
from config import Config
from database import init_database


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db = tmp_path / "cli.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()
    set_process_function(lambda job: {"status": "done", "expanded_count": 1})
    jobs_mod.stop_worker_loop(timeout=1.0)
    yield
    jobs_mod.stop_worker_loop(timeout=1.0)
    set_process_function(None)


def test_cli_jobs_create_and_status(capsys):
    code = main(["jobs", "create", "--url", "https://example.com/v", "--wait"])
    out = capsys.readouterr().out
    assert code == 0
    assert "done" in out


def test_cli_jobs_list(capsys):
    main(["jobs", "create", "--url", "https://example.com/x", "--wait"])
    code = main(["jobs", "list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "done" in out
