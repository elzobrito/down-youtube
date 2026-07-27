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
