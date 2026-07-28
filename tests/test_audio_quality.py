"""Unit tests for best-quality audio download presets."""

from pathlib import Path

from core.downloader import (
    Downloader,
    AUDIO_FORMAT_BEST,
    AUDIO_FORMAT_COMPAT,
    VIDEO_CLIENTS_BEST,
    VIDEO_CLIENTS_COMPAT,
)


def test_audio_format_spec_compat_vs_best():
    assert Downloader.audio_format_spec(False) == AUDIO_FORMAT_COMPAT
    assert Downloader.audio_format_spec(True) == AUDIO_FORMAT_BEST
    assert Downloader.audio_format_spec(False) == "bestaudio/best"
    assert Downloader.audio_format_spec(True) == "ba/b"


def test_audio_player_clients_and_sort():
    assert Downloader.audio_player_clients(False) == VIDEO_CLIENTS_COMPAT
    assert Downloader.audio_player_clients(True) == VIDEO_CLIENTS_BEST
    assert Downloader.audio_format_sort(False) is None
    assert Downloader.audio_format_sort(True) == ["abr", "asr"]


def test_download_audio_compat_uses_wav_postprocessor(monkeypatch, tmp_path):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            wav = tmp_path / "x.wav"
            wav.write_bytes(b"RIFF")
            return {"id": "x"}

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, info = Downloader().download_audio(
        "https://www.youtube.com/watch?v=x",
        str(tmp_path),
        best_quality=False,
    )
    assert path.endswith("x.wav")
    assert info["id"] == "x"
    assert captured["opts"]["format"] == AUDIO_FORMAT_COMPAT
    assert captured["opts"]["postprocessors"]
    assert captured["opts"]["postprocessors"][0]["preferredcodec"] == "wav"
    assert captured["opts"]["extractor_args"]["youtube"]["player_client"] == VIDEO_CLIENTS_COMPAT


def test_download_audio_best_converts_to_wav_and_keeps_archive(monkeypatch, tmp_path):
    captured = {}
    source = tmp_path / "vid.m4a"
    source.write_bytes(b"fake-m4a")

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            return {"id": "vid"}

    class FakeAudio:
        def __init__(self, *args, **kwargs):
            pass

        def convert_to_wav(self, input_path, output_dir, base_name, status_message=""):
            out = Path(output_dir) / f"{base_name}.wav"
            out.write_bytes(b"RIFF")
            return str(out)

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("core.audio.AudioProcessor", FakeAudio)

    dl = Downloader()
    path, info = dl.download_audio(
        "https://www.youtube.com/watch?v=vid",
        str(tmp_path),
        best_quality=True,
        keep_archive=True,
    )
    assert path.endswith("vid.wav")
    assert info["id"] == "vid"
    assert captured["opts"]["format"] == AUDIO_FORMAT_BEST
    assert captured["opts"]["format_sort"] == ["abr", "asr"]
    assert captured["opts"]["postprocessors"] == []
    assert captured["opts"]["extractor_args"]["youtube"]["player_client"] == VIDEO_CLIENTS_BEST
    assert dl.last_archive_audio_path.endswith("vid.m4a")
    assert Path(dl.last_archive_audio_path).exists()


def test_download_audio_best_without_archive_removes_source(monkeypatch, tmp_path):
    source = tmp_path / "z.m4a"
    source.write_bytes(b"fake")

    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            return {"id": "z"}

    class FakeAudio:
        def __init__(self, *args, **kwargs):
            pass

        def convert_to_wav(self, input_path, output_dir, base_name, status_message=""):
            out = Path(output_dir) / f"{base_name}.wav"
            out.write_bytes(b"RIFF")
            return str(out)

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)
    monkeypatch.setattr("core.audio.AudioProcessor", FakeAudio)

    dl = Downloader()
    path, _ = dl.download_audio(
        "https://www.youtube.com/watch?v=z",
        str(tmp_path),
        best_quality=True,
        keep_archive=False,
    )
    assert path.endswith("z.wav")
    assert dl.last_archive_audio_path is None
    assert not source.exists()


def test_streaming_ytdlp_command_best_quality():
    from core.streaming_downloader import StreamingDownloader

    cmd = StreamingDownloader()._build_ytdlp_command(
        "https://www.youtube.com/watch?v=abc",
        None,
        best_quality=True,
    )
    assert "--format" in cmd
    idx = cmd.index("--format")
    assert cmd[idx + 1] == AUDIO_FORMAT_BEST
    assert any("player_client=web" in c for c in cmd)
    assert "-S" in cmd


def test_best_quality_keep_audio_skips_streaming(monkeypatch, tmp_path):
    """Matrix: best_quality + keep_audio + streaming-on → traditional path."""
    from core.worker import TranscriberWorker
    from config import Config
    from database import init_database, set_setting

    db = tmp_path / "aq.db"
    out = tmp_path / "out"
    out.mkdir()
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()
    set_setting("use_streaming_pipeline", "1")
    set_setting("audio_download_best_quality", "1")
    set_setting("keep_audio", "1")
    set_setting("keep_video", "0")
    set_setting("output_dir", str(out))
    set_setting("ffmpeg_path", "ffmpeg")
    set_setting("whisper_cli", "whisper-cli")
    set_setting("whisper_model", "tiny")

    modes = []
    archive_path = tmp_path / "vid.m4a"
    archive_path.write_bytes(b"m4a")
    wav_path = out / "vid.wav"
    wav_path.write_bytes(b"RIFF")

    class FakeStreaming:
        def __init__(self, *a, **k):
            pass

        def download_and_convert_streaming(self, *a, **k):
            modes.append("streaming")
            return str(wav_path), {"id": "vid", "title": "t"}

    class FakeDL:
        last_archive_audio_path = str(archive_path)
        last_error = None

        def __init__(self, *a, **k):
            pass

        @staticmethod
        def resolve_source_site(info, url=""):
            return Downloader.resolve_source_site(info, url)

        def download_audio(self, *a, **k):
            modes.append("traditional")
            return str(wav_path), {"id": "vid", "title": "t", "extractor_key": "Youtube"}

        def download_video(self, *a, **k):
            raise AssertionError("should not download video")

    class FakeAudio:
        def __init__(self, *a, **k):
            pass

        def normalize_audio(self, path, output_dir):
            return path

        def convert_to_wav(self, *a, **k):
            return str(wav_path)

        def get_wav_duration(self, path):
            return 1.0

    class FakeTranscriber:
        last_segments = []
        last_error = None

        def __init__(self, *a, **k):
            pass

        def transcribe(self, audio_path, output_dir, duration=None):
            txt = Path(output_dir) / "out.txt"
            txt.write_text("hello world", encoding="utf-8")
            return str(txt)

    monkeypatch.setattr("core.worker.StreamingDownloader", FakeStreaming)
    monkeypatch.setattr("core.worker.Downloader", FakeDL)
    monkeypatch.setattr("core.worker.AudioProcessor", FakeAudio)
    monkeypatch.setattr("core.worker.Transcriber", FakeTranscriber)

    worker = TranscriberWorker(lambda m: None, lambda p: None, lambda: None)
    # Avoid hash/duplicate and real whisper settings edge cases
    monkeypatch.setattr(worker, "_hash_file", lambda p: "hash1")
    monkeypatch.setattr(
        "core.worker.get_transcription_by_audio_hash", lambda h: None
    )
    monkeypatch.setattr(
        "core.worker.get_latest_transcription_for_source", lambda **k: None
    )

    result = worker.processar_url("https://www.youtube.com/watch?v=vid")
    assert result == "success"
    assert modes == ["traditional"]
    assert "streaming" not in modes
    assert archive_path.exists()
    Config._instance = None


def test_streaming_still_used_without_keep_audio(monkeypatch, tmp_path):
    from core.worker import TranscriberWorker
    from config import Config
    from database import init_database, set_setting

    db = tmp_path / "aq2.db"
    out = tmp_path / "out"
    out.mkdir()
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()
    set_setting("use_streaming_pipeline", "1")
    set_setting("audio_download_best_quality", "1")
    set_setting("keep_audio", "0")
    set_setting("keep_video", "0")
    set_setting("output_dir", str(out))
    set_setting("ffmpeg_path", "ffmpeg")
    set_setting("whisper_cli", "whisper-cli")
    set_setting("whisper_model", "tiny")

    modes = []
    wav_path = out / "vid.wav"
    wav_path.write_bytes(b"RIFF")

    class FakeStreaming:
        def __init__(self, *a, **k):
            pass

        def download_and_convert_streaming(self, *a, **k):
            modes.append("streaming")
            return str(wav_path), {"id": "vid", "title": "t", "extractor_key": "Youtube"}

    class FakeDL:
        last_archive_audio_path = None
        last_error = None

        def __init__(self, *a, **k):
            pass

        @staticmethod
        def resolve_source_site(info, url=""):
            return Downloader.resolve_source_site(info, url)

        def download_audio(self, *a, **k):
            modes.append("traditional")
            return str(wav_path), {"id": "vid", "title": "t"}

    class FakeAudio:
        def __init__(self, *a, **k):
            pass

        def normalize_audio(self, path, output_dir):
            return path

        def get_wav_duration(self, path):
            return 1.0

    class FakeTranscriber:
        last_segments = []
        last_error = None

        def __init__(self, *a, **k):
            pass

        def transcribe(self, audio_path, output_dir, duration=None):
            txt = Path(output_dir) / "out.txt"
            txt.write_text("hello", encoding="utf-8")
            return str(txt)

    monkeypatch.setattr("core.worker.StreamingDownloader", FakeStreaming)
    monkeypatch.setattr("core.worker.Downloader", FakeDL)
    monkeypatch.setattr("core.worker.AudioProcessor", FakeAudio)
    monkeypatch.setattr("core.worker.Transcriber", FakeTranscriber)

    worker = TranscriberWorker(lambda m: None, lambda p: None, lambda: None)
    monkeypatch.setattr(worker, "_hash_file", lambda p: "hash2")
    monkeypatch.setattr("core.worker.get_transcription_by_audio_hash", lambda h: None)
    monkeypatch.setattr("core.worker.get_latest_transcription_for_source", lambda **k: None)

    result = worker.processar_url("https://www.youtube.com/watch?v=vid")
    assert result == "success"
    assert modes == ["streaming"]
    Config._instance = None
