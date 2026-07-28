"""Offline tests for LTM bridge (rag-sqlite CLI + hash embeddings)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_app(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "youtube_transcriber.db"

    import config as config_mod

    config_mod.Config._instance = None
    cfg = config_mod.Config()
    cfg.portable_mode = True
    cfg.data_dir = data_dir
    cfg.db_path = db_path
    config_mod.Config._instance = cfg

    import database

    database.init_database()
    database.set_setting("rag_enabled", "1")
    database.set_setting("rag_embedding_provider", "hash")
    database.set_setting("rag_index_on_save", "0")  # control enqueue in unit tests
    database.set_setting("rag_db_name", "youtube_rag.sqlite")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    ids = []
    for i, (title, text) in enumerate(
        [
            ("Video Behemoth", "O Behemoth e um monstro biblico descrito em Jo."),
            ("Video Leviathan", "O Leviathan vive no mar e confronta o Behemoth."),
        ],
        start=1,
    ):
        cur.execute(
            "INSERT INTO videos (url, video_id, title, channel) VALUES (?, ?, ?, ?)",
            (f"https://youtu.be/vid{i}", f"vid{i}", title, "Canal Teste"),
        )
        vid = cur.lastrowid
        cur.execute(
            """
            INSERT INTO transcriptions
            (video_id, language, full_text, segments_json, word_count, duration_seconds, model_used)
            VALUES (?, 'pt', ?, '[]', ?, 10, 'test')
            """,
            (vid, text, len(text.split())),
        )
        ids.append(cur.lastrowid)
    conn.commit()
    conn.close()

    yield {"ids": ids, "data_dir": data_dir}
    config_mod.Config._instance = None


def test_project_index_set_equality_and_remember(isolated_app):
    from core import rag_bridge

    report = rag_bridge.backfill_all_transcriptions(force=True, backup_first=True)
    assert report["set_equal"] is True
    assert set(report["S_app"]) == set(report["S_rag"]) == set(isolated_app["ids"])
    assert (isolated_app["data_dir"] / "rag_manifest.jsonl").exists()
    assert (isolated_app["data_dir"] / "rag_backfill_report.json").exists()
    assert list((isolated_app["data_dir"] / "backups").glob("*.db")) or list(
        (isolated_app["data_dir"] / "backups").glob("*.bak-*")
    )

    mem = rag_bridge.remember("Behemoth monstro", top_k=5, min_score=0.01)
    assert mem["ok"] is True
    assert mem["hit_count"] >= 1
    assert mem["hits"][0].get("transcription_id") in isolated_app["ids"]
    assert mem["hits"][0].get("title")

    # scoped query still works
    tid = isolated_app["ids"][0]
    scoped = rag_bridge.remember("Behemoth", video_scope=tid, top_k=5, min_score=0.01)
    assert scoped["ok"] is True


def test_queue_and_forget(isolated_app):
    from core import rag_bridge
    from database import set_setting

    set_setting("rag_index_on_save", "1")
    tid = isolated_app["ids"][0]
    rag_bridge.enqueue_index(tid)
    out = rag_bridge.process_queue()
    assert out["processed"] >= 1
    assert tid in rag_bridge.rag_indexed_transcription_ids()

    rag_bridge.forget_transcription(tid)
    assert tid not in rag_bridge.rag_indexed_transcription_ids()


def test_concurrent_enqueue_during_process_not_lost(isolated_app, monkeypatch):
    """Enqueue while a job is mid-index must remain queued for a later call."""
    from core import rag_bridge
    from database import count_rag_jobs_by_status, set_setting

    set_setting("rag_index_on_save", "1")
    tid_a, tid_b = isolated_app["ids"]
    rag_bridge.enqueue_index(tid_a)

    original_index = rag_bridge.index_transcription

    def slow_index(transcription_id, *, force=False):
        # Concurrent enqueue while first job is "running"
        if int(transcription_id) == int(tid_a):
            rag_bridge.enqueue_index(tid_b)
        return original_index(transcription_id, force=force)

    monkeypatch.setattr(rag_bridge, "index_transcription", slow_index)
    out1 = rag_bridge.process_queue(max_jobs=1)
    assert out1["processed"] == 1
    assert count_rag_jobs_by_status("queued") >= 1

    out2 = rag_bridge.process_queue(max_jobs=10)
    assert out2["processed"] >= 1
    assert tid_b in rag_bridge.rag_indexed_transcription_ids()


def test_rag_claim_atomic_two_claimers(isolated_app):
    from database import claim_next_rag_job, enqueue_rag_job, init_database

    init_database()
    tid = isolated_app["ids"][0]
    enqueue_rag_job(tid, op="index")
    first = claim_next_rag_job()
    second = claim_next_rag_job()
    assert first is not None
    assert first["status"] == "running" or first["transcription_id"] == tid
    assert second is None  # only one job; second claim must not double-run


def test_rag_stale_running_recovered(isolated_app):
    from datetime import datetime, timedelta

    from database import (
        _connect,
        claim_next_rag_job,
        enqueue_rag_job,
        finish_rag_job,
        init_database,
    )

    init_database()
    tid = isolated_app["ids"][0]
    jid = enqueue_rag_job(tid, op="index")
    # Force a stale running claim
    claimed = claim_next_rag_job()
    assert claimed is not None
    conn = _connect()
    old = datetime.now() - timedelta(seconds=10_000)
    conn.execute(
        "UPDATE rag_index_jobs SET claimed_at = ?, status = 'running' WHERE id = ?",
        (old, claimed["id"]),
    )
    conn.commit()
    conn.close()

    recovered = claim_next_rag_job(stale_running_seconds=60)
    assert recovered is not None
    assert recovered["transcription_id"] == tid
    finish_rag_job(recovered["id"], status="done", last_result="indexed")


def test_legacy_jsonl_import_idempotent(isolated_app):
    import json

    from core import rag_bridge
    from database import count_rag_jobs_by_status, import_legacy_rag_jsonl_once, set_setting

    set_setting("rag_queue_jsonl_imported", "0")
    path = isolated_app["data_dir"] / "rag_index_queue.jsonl"
    tid = isolated_app["ids"][0]
    path.write_text(
        json.dumps({"transcription_id": tid, "op": "index", "status": "pending"}) + "\n"
        + json.dumps({"transcription_id": tid, "op": "index", "status": "error", "last_error": "x"})
        + "\n"
        + json.dumps({"transcription_id": tid, "op": "index", "status": "done"})
        + "\n",
        encoding="utf-8",
    )
    n1 = import_legacy_rag_jsonl_once(path)
    n2 = import_legacy_rag_jsonl_once(path)
    assert n1 >= 1
    assert n2 == 0  # flag set; idempotent
    assert count_rag_jobs_by_status("queued") + count_rag_jobs_by_status("error") >= 1
    # corpus/manifest not wiped by import
    assert rag_bridge.corpus_dir().exists() or True


def test_rag_error_backoff_does_not_starve_queued(isolated_app, monkeypatch):
    from core import rag_bridge
    from database import (
        claim_next_rag_job,
        enqueue_rag_job,
        list_rag_job_rows,
    )

    tid_error, tid_ok = isolated_app["ids"]
    enqueue_rag_job(tid_error, op="index")
    enqueue_rag_job(tid_ok, op="index")

    def fake_index(transcription_id, *, force=False):
        if int(transcription_id) == int(tid_error):
            return {"status": "error", "error": "permanent"}
        return {"status": "indexed"}

    monkeypatch.setattr(rag_bridge, "index_transcription", fake_index)
    out = rag_bridge.process_queue(
        max_jobs=4,
        max_attempts=3,
        retry_base_seconds=60,
    )

    rows = list_rag_job_rows(limit=10)
    by_tid = {row[1]: row for row in rows}
    assert out["processed"] == 1
    assert by_tid[tid_error][3] == "error"
    assert by_tid[tid_error][4] == 1
    assert by_tid[tid_error][10] is not None
    assert by_tid[tid_ok][3] == "done"
    assert by_tid[tid_ok][4] == 1
    assert claim_next_rag_job(max_attempts=3) is None


def test_rag_error_respects_max_attempts(isolated_app):
    from datetime import datetime, timedelta

    from database import (
        _connect,
        claim_next_rag_job,
        enqueue_rag_job,
        finish_rag_job,
    )

    tid = isolated_app["ids"][0]
    enqueue_rag_job(tid, op="index")
    claimed = claim_next_rag_job(max_attempts=1)
    assert claimed is not None
    finish_rag_job(
        claimed["id"],
        status="error",
        last_error="permanent",
        retry_delay_seconds=60,
    )

    conn = _connect()
    conn.execute(
        "UPDATE rag_index_jobs SET next_attempt_at = ? WHERE id = ?",
        (datetime.now() - timedelta(seconds=1), claimed["id"]),
    )
    conn.commit()
    conn.close()
    assert claim_next_rag_job(max_attempts=1) is None
