"""Tests for YouTube single-video vs playlist URL handling (YT-PLAYLIST-001)."""

from __future__ import annotations

from contextlib import contextmanager

from core.url_resolver import (
    canonicalize_watch_url,
    classify_youtube_url,
    expand_input_urls,
    expand_playlist_entries,
    is_youtube_url,
)


def test_classify_single_video():
    assert (
        classify_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        == "single_video"
    )
    assert classify_youtube_url("https://youtu.be/dQw4w9WgXcQ") == "single_video"
    assert (
        classify_youtube_url("https://www.youtube.com/shorts/abc123xyz00")
        == "single_video"
    )


def test_classify_playlist_page():
    assert (
        classify_youtube_url(
            "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxx"
        )
        == "playlist"
    )


def test_classify_video_with_list_context():
    assert (
        classify_youtube_url(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxx&index=2"
        )
        == "video_with_playlist_context"
    )


def test_canonicalize_strips_list():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxx&index=3"
    assert canonicalize_watch_url(url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_expand_playlist_mock():
    class FakeYDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            assert "playlist" in url or "list=" in url
            return {
                "_type": "playlist",
                "entries": [
                    {"id": "aaa111bbb22"},
                    {"id": "ccc222ddd33"},
                    {"id": "eee333fff44"},
                ],
            }

    urls = expand_playlist_entries(
        "https://www.youtube.com/playlist?list=PLtest",
        ydl_factory=FakeYDL,
    )
    assert urls == [
        "https://www.youtube.com/watch?v=aaa111bbb22",
        "https://www.youtube.com/watch?v=ccc222ddd33",
        "https://www.youtube.com/watch?v=eee333fff44",
    ]


def test_expand_input_playlist_to_n_jobs():
    class FakeYDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return {
                "entries": [{"id": "vid1xxxx01"}, {"id": "vid2xxxx02"}],
            }

    out = expand_input_urls(
        ["https://www.youtube.com/playlist?list=PLabc"],
        ydl_factory=FakeYDL,
    )
    assert len(out) == 2
    assert all(u.startswith("https://www.youtube.com/watch?v=") for u in out)


def test_expand_watch_with_list_default_single():
    out = expand_input_urls(
        ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxx"],
        expand_watch_list=False,
    )
    assert out == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]


def test_expand_watch_with_list_expand_flag():
    class FakeYDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return {"entries": [{"id": "a1"}, {"id": "b2"}, {"id": "c3"}]}

    out = expand_input_urls(
        ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxx"],
        expand_watch_list=True,
        ydl_factory=FakeYDL,
    )
    assert len(out) == 3


def test_single_video_unchanged_count():
    out = expand_input_urls(["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    assert out == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]


def test_is_youtube_url():
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert not is_youtube_url("https://example.com/x")
    assert not is_youtube_url("/tmp/local.wav")


def test_worker_processar_lista_expands(monkeypatch):
    """Worker flattens playlist into N processar_url calls."""
    from core import worker as worker_mod
    from core.worker import TranscriberWorker

    class FakeYDL:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            return {"entries": [{"id": "w1"}, {"id": "w2"}]}

    calls = []

    def fake_expand(items, **kwargs):
        return expand_input_urls(items, ydl_factory=FakeYDL)

    monkeypatch.setattr(
        "core.url_resolver.expand_input_urls",
        fake_expand,
    )

    w = TranscriberWorker(
        log_callback=lambda m: None,
        progress_callback=lambda m: None,
        complete_callback=None,
        confirm_callback=lambda t, m: False,
    )
    w._get_current_config = lambda: {"cookies_path": None}
    w.processar_url = lambda url: calls.append(url) or "success"
    w.processar_arquivo_local = lambda p: "success"
    w._notify = lambda *a, **k: None

    summary = w.processar_lista(["https://www.youtube.com/playlist?list=PLtest"])
    assert summary["success"] == 2
    assert calls == [
        "https://www.youtube.com/watch?v=w1",
        "https://www.youtube.com/watch?v=w2",
    ]
