from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture()
def improvement_app(tmp_path, monkeypatch):
    import config as config_mod
    import database
    from core import rag_bridge

    config_mod.Config._instance = None
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    cfg = config_mod.Config()
    cfg.portable_mode = True
    cfg.data_dir = data_dir
    cfg.db_path = data_dir / "youtube_transcriber.db"
    config_mod.Config._instance = cfg
    database.init_database()
    database.set_setting("rag_enabled", "0")

    conn = sqlite3.connect(str(cfg.db_path))
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO videos (url, video_id, title, channel)
        VALUES ('https://youtu.be/integration', 'integration', 'SSH pratico', 'Canal')
        """
    )
    video_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO transcriptions (
            video_id, language, full_text, segments_json, word_count,
            duration_seconds, model_used
        )
        VALUES (
            ?, 'pt', 'o comando calcei abre uma vaca',
            '[{"start":0,"end":3,"text":"o comando calcei abre uma vaca"}]',
            7, 3, 'small'
        )
        """,
        (video_id,),
    )
    transcription_id = cur.lastrowid
    conn.commit()
    conn.close()

    reindex_calls = []
    monkeypatch.setattr(
        rag_bridge,
        "on_transcription_saved",
        lambda tid: reindex_calls.append(tid),
    )
    yield database, transcription_id, reindex_calls
    config_mod.Config._instance = None


def _draft(database, transcription_id):
    return database.create_transcription_revision(
        transcription_id,
        model="phi4-mini:latest",
        prompt_version="prompt-test",
        glossary_version="glossary-test",
        improved_text="o comando cowsay abre uma vaca revisada",
        improved_segments=[
            {
                "start": 0,
                "end": 3,
                "text": "o comando cowsay abre uma vaca revisada",
            }
        ],
        study_markdown="# SSH\n\nUse `cowsay` para o exemplo.",
        proposals={"version": 1, "segments": [], "proposals": []},
        decisions={"selected_proposal_ids": []},
        outtakes=[],
        chunk_count=1,
        usage={"elapsed_seconds": 0.5},
    )


def test_draft_does_not_change_search_chat_or_views(improvement_app, monkeypatch):
    database, transcription_id, reindex_calls = improvement_app
    _draft(database, transcription_id)
    loaded = database.get_transcription(transcription_id)

    assert database.search_transcriptions("calcei")
    assert not database.search_transcriptions("revisada")
    assert loaded["effective_text"] == loaded["full_text"]
    assert reindex_calls == []

    from gui.tabs.chat_tab import ChatWindow
    import gui.tabs.chat_tab as chat_tab
    from gui.tabs.library_tab import select_transcription_view

    monkeypatch.setattr(
        chat_tab,
        "get_setting",
        lambda key: {
            "rag_enabled": "0",
            "rag_fallback_full_text": "1",
            "rag_max_context_chars": "16000",
        }.get(key),
    )
    window = object.__new__(ChatWindow)
    window.transcription = loaded
    window.library_scope_var = type("Scope", (), {"get": lambda self: False})()
    context, _status = window._build_memory_context("comando")
    assert "calcei" in context
    assert "revisada" not in context

    original, original_segments, label = select_transcription_view(
        loaded, "Aprimorada"
    )
    assert label == "Original"
    assert original == loaded["full_text"]
    assert original_segments == loaded["segments"]


def test_approval_switches_downstream_and_deactivate_restores_original(
    improvement_app,
):
    database, transcription_id, reindex_calls = improvement_app
    revision = _draft(database, transcription_id)
    database.approve_transcription_revision(revision["id"])

    loaded = database.get_transcription(transcription_id)
    assert loaded["effective_text"].endswith("revisada")
    assert loaded["effective_segments"][0]["text"].endswith("revisada")
    assert loaded["study_markdown"].startswith("# SSH")
    assert database.search_transcriptions("revisada")
    assert not database.search_transcriptions("calcei")
    assert database.get_all_transcriptions()[0][4] == 7
    assert database.get_transcription_stats()["total_words"] == 7
    assert reindex_calls == [transcription_id]

    from core.rag_bridge import _build_markdown
    from gui.tabs.library_tab import select_transcription_view

    markdown = _build_markdown(loaded)
    assert f"revision_id: {revision['id']}" in markdown
    assert "text_version: improved" in markdown
    assert "revisada" in markdown
    assert "calcei" not in markdown

    improved, segments, label = select_transcription_view(loaded, "Aprimorada")
    assert label == "Aprimorada"
    assert improved == loaded["effective_text"]
    assert segments == loaded["effective_segments"]
    study, _segments, label = select_transcription_view(loaded, "Estudo")
    assert label == "Estudo"
    assert study.startswith("# SSH")

    database.deactivate_transcription_revision(transcription_id)
    restored = database.get_transcription(transcription_id)
    assert restored["active_revision"] is None
    assert restored["effective_text"] == restored["full_text"]
    assert reindex_calls == [transcription_id, transcription_id]


def test_reject_schedules_rag_without_changing_effective_text(improvement_app):
    database, transcription_id, reindex_calls = improvement_app
    revision = _draft(database, transcription_id)
    database.reject_transcription_revision(revision["id"])

    loaded = database.get_transcription(transcription_id)
    assert loaded["effective_text"] == loaded["full_text"]
    assert database.get_transcription_revision(revision["id"])["status"] == "rejected"
    assert reindex_calls == [transcription_id]


def test_markdown_export_writes_visible_version(tmp_path):
    from core.exporter import Exporter

    target = tmp_path / "estudo.md"
    Exporter.to_markdown("# Estudo\n\n`ssh -D 1337`", target)
    assert target.read_text(encoding="utf-8") == "# Estudo\n\n`ssh -D 1337`"
