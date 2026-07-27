"""Unit tests for video download quality presets (yt-dlp format selection)."""

from core.downloader import (
    Downloader,
    VIDEO_FORMAT_BEST,
    VIDEO_FORMAT_COMPAT,
    VIDEO_CLIENTS_BEST,
    VIDEO_CLIENTS_COMPAT,
)


def test_video_format_spec_compat_vs_best():
    assert Downloader.video_format_spec(False) == VIDEO_FORMAT_COMPAT
    assert Downloader.video_format_spec(True) == VIDEO_FORMAT_BEST
    assert Downloader.video_format_spec(False) == "bestvideo+bestaudio/best"
    assert Downloader.video_format_spec(True) == "bv*+ba/b"


def test_video_merge_format_mp4_vs_mkv():
    assert Downloader.video_merge_format(False) == "mp4"
    assert Downloader.video_merge_format(True) == "mkv"


def test_video_player_clients_prefer_higher_ladders_when_best():
    compat = Downloader.video_player_clients(False)
    best = Downloader.video_player_clients(True)
    assert compat == VIDEO_CLIENTS_COMPAT
    assert best == VIDEO_CLIENTS_BEST
    assert "android" in compat
    assert best[0] in {"web", "web_safari", "tv"}
    assert "android" in best


def test_download_video_passes_best_quality_opts(monkeypatch, tmp_path):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            # Simulate merged output next to outtmpl id
            out = tmp_path / "vid123.mkv"
            out.write_bytes(b"fake")
            return {"id": "vid123", "display_id": "vid123"}

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, info = Downloader().download_video(
        "https://www.youtube.com/watch?v=vid123",
        str(tmp_path),
        best_quality=True,
    )
    assert path and path.endswith("vid123.mkv")
    assert info["id"] == "vid123"
    assert captured["opts"]["format"] == VIDEO_FORMAT_BEST
    assert captured["opts"]["merge_output_format"] == "mkv"
    assert captured["opts"]["extractor_args"]["youtube"]["player_client"] == VIDEO_CLIENTS_BEST


def test_download_video_compat_defaults(monkeypatch, tmp_path):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            out = tmp_path / "abc.mp4"
            out.write_bytes(b"fake")
            return {"id": "abc"}

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, _info = Downloader().download_video(
        "https://www.youtube.com/watch?v=abc",
        str(tmp_path),
        best_quality=False,
    )
    assert path.endswith("abc.mp4")
    assert captured["opts"]["format"] == VIDEO_FORMAT_COMPAT
    assert captured["opts"]["merge_output_format"] == "mp4"
    assert captured["opts"]["extractor_args"]["youtube"]["player_client"] == VIDEO_CLIENTS_COMPAT


def test_download_audio_format_unchanged_by_best_quality_flag(monkeypatch, tmp_path):
    """Audio transcription path must stay bestaudio/best regardless of video flag."""
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            wav = tmp_path / "aud.wav"
            wav.write_bytes(b"RIFF")
            return {"id": "aud"}

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, _ = Downloader().download_audio(
        "https://www.youtube.com/watch?v=aud",
        str(tmp_path),
    )
    assert path
    assert captured["opts"]["format"] == "bestaudio/best"
