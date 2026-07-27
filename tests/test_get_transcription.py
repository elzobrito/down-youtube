"""Regression: get_transcription must return correct video metadata after is_used."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "youtube_transcriber.db"

    import config as config_mod

    # Force Config singleton onto tmp data dir
    config_mod.Config._instance = None
    cfg = config_mod.Config()
    cfg.portable_mode = True
    cfg.data_dir = data_dir
    cfg.db_path = db_path
    config_mod.Config._instance = cfg

    import database

    database.init_database()
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO videos (url, video_id, title, channel, audio_path, video_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "https://youtu.be/abc123",
            "abc123",
            "Titulo Correto Do Video",
            "Canal Correto",
            None,
            None,
        ),
    )
    video_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO transcriptions
        (video_id, language, full_text, segments_json, word_count, duration_seconds,
         model_used, audio_hash, is_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video_id,
            "portuguese",
            "texto da transcricão de teste",
            "[]",
            5,
            12.5,
            "model-x",
            "hashdeadbeef",
            1,
        ),
    )
    tid = cur.lastrowid
    conn.commit()
    conn.close()
    yield tid, video_id
    config_mod.Config._instance = None


def test_get_transcription_metadata_not_shifted(app_db):
    tid, video_id = app_db
    import database

    row = database.get_transcription(tid)
    assert row is not None
    assert row["id"] == tid
    assert row["video_id"] == video_id
    assert row["video_title"] == "Titulo Correto Do Video"
    assert row["video_url"] == "https://youtu.be/abc123"
    assert row["channel"] == "Canal Correto"
    assert row["full_text"] == "texto da transcricão de teste"
    assert row["language"] == "portuguese"
    assert row["model"] == "model-x"
    assert row["audio_hash"] == "hashdeadbeef"
    assert row["is_used"] == 1
    assert row["youtube_video_id"] == "abc123"
    # Must not confuse updated_at/is_used with title
    assert row["video_title"] not in (None, 0, "0", "")
