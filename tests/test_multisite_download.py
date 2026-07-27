"""Site-aware yt-dlp options: YouTube extractor_args only for YouTube hosts."""

from core.downloader import (
    Downloader,
    VIDEO_CLIENTS_BEST,
    VIDEO_CLIENTS_COMPAT,
    VIDEO_FORMAT_BEST,
    AUDIO_FORMAT_COMPAT,
)
from core.streaming_downloader import StreamingDownloader
from core.url_resolver import expand_input_urls, is_youtube_url


YT_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
VIMEO_URL = "https://vimeo.com/123456789"
SOUNDCLOUD_URL = "https://soundcloud.com/artist/track-name"


def test_uses_youtube_extractor_only_for_youtube_hosts():
    assert Downloader.uses_youtube_extractor(YT_URL) is True
    assert Downloader.uses_youtube_extractor("https://youtu.be/dQw4w9WgXcQ") is True
    assert Downloader.uses_youtube_extractor(VIMEO_URL) is False
    assert Downloader.uses_youtube_extractor(SOUNDCLOUD_URL) is False
    assert Downloader.uses_youtube_extractor("") is False


def test_youtube_extractor_args_present_only_for_youtube():
    args = Downloader.youtube_extractor_args(YT_URL, VIDEO_CLIENTS_BEST)
    assert args == {"youtube": {"player_client": VIDEO_CLIENTS_BEST}}

    assert Downloader.youtube_extractor_args(VIMEO_URL, VIDEO_CLIENTS_BEST) is None
    assert Downloader.youtube_extractor_args(SOUNDCLOUD_URL, VIDEO_CLIENTS_COMPAT) is None


def test_resolve_source_site_prefers_extractor_key():
    assert Downloader.resolve_source_site({"extractor_key": "vimeo"}, VIMEO_URL) == "vimeo"
    assert Downloader.resolve_source_site({"extractor_key": "Youtube"}, YT_URL) == "youtube"
    assert Downloader.resolve_source_site(None, VIMEO_URL) == "vimeo.com"
    assert Downloader.resolve_source_site(None, YT_URL) == "youtube"
    assert Downloader.resolve_source_site(None, "") == "unknown"


def test_download_video_youtube_keeps_extractor_args(monkeypatch, tmp_path):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            out = tmp_path / "vid123.mkv"
            out.write_bytes(b"fake")
            return {"id": "vid123", "extractor_key": "Youtube"}

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, info = Downloader().download_video(YT_URL, str(tmp_path), best_quality=True)
    assert path and path.endswith("vid123.mkv")
    assert captured["opts"]["format"] == VIDEO_FORMAT_BEST
    assert captured["opts"]["extractor_args"]["youtube"]["player_client"] == VIDEO_CLIENTS_BEST
    assert Downloader.resolve_source_site(info, YT_URL) == "youtube"


def test_download_video_vimeo_has_no_youtube_extractor_args(monkeypatch, tmp_path):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            out = tmp_path / "vimeo1.mp4"
            out.write_bytes(b"fake")
            return {
                "id": "vimeo1",
                "extractor_key": "vimeo",
                "title": "Demo Vimeo",
            }

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, info = Downloader().download_video(VIMEO_URL, str(tmp_path), best_quality=False)
    assert path and path.endswith("vimeo1.mp4")
    assert "extractor_args" not in captured["opts"]
    assert Downloader.resolve_source_site(info, VIMEO_URL) == "vimeo"


def test_download_audio_non_youtube_no_youtube_extractor(monkeypatch, tmp_path):
    captured = {}

    class FakeYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            wav = tmp_path / "sc1.wav"
            wav.write_bytes(b"RIFF")
            return {"id": "sc1", "extractor_key": "soundcloud"}

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)

    path, info = Downloader().download_audio(SOUNDCLOUD_URL, str(tmp_path))
    assert path
    assert captured["opts"]["format"] == AUDIO_FORMAT_COMPAT
    assert "extractor_args" not in captured["opts"]
    assert Downloader.resolve_source_site(info, SOUNDCLOUD_URL) == "soundcloud"


def test_streaming_command_youtube_has_extractor_args():
    cmd = StreamingDownloader()._build_ytdlp_command(YT_URL, None, best_quality=False)
    joined = " ".join(cmd)
    assert "--extractor-args" in cmd
    assert "youtube:player_client=" in joined


def test_streaming_command_vimeo_omits_youtube_extractor_args():
    cmd = StreamingDownloader()._build_ytdlp_command(VIMEO_URL, None, best_quality=True)
    joined = " ".join(cmd)
    assert "--extractor-args" not in cmd
    assert "youtube:player_client" not in joined
    assert "-S" in cmd  # best_quality sort still applies


def test_expand_input_urls_passthrough_non_youtube():
    out = expand_input_urls([VIMEO_URL, SOUNDCLOUD_URL])
    assert out == [VIMEO_URL, SOUNDCLOUD_URL]
    assert not is_youtube_url(VIMEO_URL)


def test_download_error_message_mentions_multisite(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            raise Exception("Unsupported URL: site.example")

    monkeypatch.setattr("core.downloader.yt_dlp.YoutubeDL", FakeYDL)
    dl = Downloader()
    path, info = dl.download_video("https://site.example/video/1", str(tmp_path))
    assert path is None and info is None
    assert dl.last_error
    assert "multi-site" in dl.last_error.lower() or "yt-dlp" in dl.last_error.lower()
