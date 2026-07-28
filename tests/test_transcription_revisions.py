from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture()
def revision_db(tmp_path):
    import config as config_mod
    import database

    config_mod.Config._instance = None
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = config_mod.Config()
    cfg.portable_mode = True
    cfg.data_dir = data_dir
    cfg.db_path = data_dir / "youtube_transcriber.db"
    config_mod.Config._instance = cfg
    database.init_database()

    conn = sqlite3.connect(str(cfg.db_path))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO videos (url, video_id, title, channel)
        VALUES ('https://youtu.be/rev', 'rev', 'Vídeo', 'Canal')
        """
    )
    video_id = cur.lastrowid
    segments = '[{"start":0,"end":2,"text":"texto calcei"}]'
    cur.execute(
        """
        INSERT INTO transcriptions (
            video_id, language, full_text, segments_json, word_count,
            duration_seconds, model_used
        )
        VALUES (?, 'pt', 'texto calcei', ?, 2, 2, 'small')
        """,
        (video_id, segments),
    )
    transcription_id = cur.lastrowid
    conn.commit()
    conn.close()
    yield database, cfg.db_path, transcription_id
    config_mod.Config._instance = None


def create_draft(database, transcription_id, text="texto cowsay"):
    return database.create_transcription_revision(
        transcription_id,
        model="phi4-mini:latest",
        prompt_version="v1",
        glossary_version="g1",
        improved_text=text,
        improved_segments=[{"start": 0, "end": 2, "text": text}],
        study_markdown=f"# Estudo\n\n{text}",
        proposals={"segments": [], "proposals": []},
        decisions={"selected_proposal_ids": []},
        outtakes=[],
        chunk_count=1,
        usage={"requests": 1},
    )


def test_migration_is_idempotent_and_original_is_immutable(revision_db):
    database, db_path, transcription_id = revision_db
    database.init_database()
    database.init_database()
    before = database.get_transcription(transcription_id)
    draft = create_draft(database, transcription_id)
    after = database.get_transcription(transcription_id)

    assert draft["status"] == "draft"
    assert draft["revision_number"] == 1
    assert after["full_text"] == before["full_text"] == "texto calcei"
    assert after["segments"] == before["segments"]
    assert after["active_revision"] is None
    assert after["effective_text"] == "texto calcei"

    conn = sqlite3.connect(str(db_path))
    indexes = {
        row[1]
        for row in conn.execute("PRAGMA index_list(transcription_revisions)")
    }
    conn.close()
    assert "idx_transcription_revision_active" in indexes


def test_approve_is_atomic_and_effective_fields_switch(revision_db):
    database, _db_path, transcription_id = revision_db
    first = create_draft(database, transcription_id, "primeira revisão")
    database.approve_transcription_revision(first["id"])
    second = create_draft(database, transcription_id, "segunda revisão")
    database.approve_transcription_revision(second["id"])

    revisions = database.list_transcription_revisions(transcription_id)
    active = [row for row in revisions if row["is_active"]]
    loaded = database.get_transcription(transcription_id)

    assert len(active) == 1
    assert active[0]["id"] == second["id"]
    assert loaded["full_text"] == "texto calcei"
    assert loaded["effective_text"] == "segunda revisão"
    assert loaded["effective_segments"][0]["text"] == "segunda revisão"
    assert loaded["study_markdown"].startswith("# Estudo")


def test_reject_and_deactivate_preserve_history(revision_db):
    database, _db_path, transcription_id = revision_db
    approved = create_draft(database, transcription_id, "aprovada")
    database.approve_transcription_revision(approved["id"])
    rejected = create_draft(database, transcription_id, "rejeitada")
    database.reject_transcription_revision(rejected["id"])

    assert database.get_transcription_revision(rejected["id"])["status"] == "rejected"
    assert database.get_transcription(transcription_id)["effective_text"] == "aprovada"

    database.deactivate_transcription_revision(transcription_id)
    loaded = database.get_transcription(transcription_id)
    assert loaded["active_revision"] is None
    assert loaded["effective_text"] == loaded["full_text"] == "texto calcei"
    assert len(database.list_transcription_revisions(transcription_id)) == 2


def test_approval_rejects_stale_source(revision_db):
    database, db_path, transcription_id = revision_db
    draft = create_draft(database, transcription_id)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE transcriptions SET full_text = 'mudou' WHERE id = ?",
        (transcription_id,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="original mudou"):
        database.approve_transcription_revision(draft["id"])


def test_delete_transcription_removes_revision_rows(revision_db):
    database, db_path, transcription_id = revision_db
    create_draft(database, transcription_id)
    database.delete_transcription(transcription_id)

    conn = sqlite3.connect(str(db_path))
    count = conn.execute(
        "SELECT COUNT(*) FROM transcription_revisions WHERE transcription_id = ?",
        (transcription_id,),
    ).fetchone()[0]
    conn.close()
    assert count == 0
