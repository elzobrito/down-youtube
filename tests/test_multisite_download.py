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
    assert Downloader.resolve_source_site(None, VIMEO_URL) == "vimeo"
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


def test_normalize_source_site_youtube_variants():
    from database import normalize_source_site

    assert normalize_source_site(source_site="Youtube") == "youtube"
    assert normalize_source_site(source_site="youtube:tab") == "youtube"
    assert normalize_source_site(info={"extractor_key": "YoutubeYtBe"}) == "youtube"
    assert normalize_source_site(url="https://www.youtube.com/watch?v=x") == "youtube"
    assert normalize_source_site(url="https://youtu.be/x") == "youtube"
    assert normalize_source_site(source_site="vimeo") == "vimeo"
    assert Downloader.resolve_source_site({"extractor_key": "Youtube"}, YT_URL) == "youtube"


def test_cross_site_same_video_id_separate_rows(tmp_path, monkeypatch):
    from config import Config
    from database import add_video, init_database, _connect

    db = tmp_path / "ms.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()

    yt = add_video(
        "https://www.youtube.com/watch?v=sameid",
        video_id="sameid",
        title="YT title",
        source_site="youtube",
    )
    vim = add_video(
        "https://vimeo.com/sameid",
        video_id="sameid",
        title="Vimeo title",
        source_site="vimeo",
    )
    assert yt != vim
    conn = _connect()
    rows = conn.execute(
        "SELECT id, source_site, title FROM videos WHERE video_id = ? ORDER BY id",
        ("sameid",),
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    sites = {r[1] for r in rows}
    assert sites == {"youtube", "vimeo"}
    titles = {r[2] for r in rows}
    assert titles == {"YT title", "Vimeo title"}

    # Update youtube only — vimeo untouched
    add_video(
        "https://www.youtube.com/watch?v=sameid",
        video_id="sameid",
        title="YT updated",
        source_site="Youtube",
    )
    conn = _connect()
    yt_row = conn.execute(
        "SELECT title FROM videos WHERE source_site = 'youtube' AND video_id = ?",
        ("sameid",),
    ).fetchone()
    vim_row = conn.execute(
        "SELECT title FROM videos WHERE source_site = 'vimeo' AND video_id = ?",
        ("sameid",),
    ).fetchone()
    conn.close()
    assert yt_row[0] == "YT updated"
    assert vim_row[0] == "Vimeo title"
    Config._instance = None


def test_duplicate_without_source_site_preserves_vimeo(tmp_path, monkeypatch):
    from config import Config
    from database import _connect, add_video, init_database

    db = tmp_path / "vimeo-identity.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()

    row_id = add_video(
        "https://vimeo.com/777",
        video_id="777",
        title="Vimeo title",
        source_site="vimeo",
    )
    assert add_video("https://vimeo.com/777") == row_id

    conn = _connect()
    row = conn.execute(
        "SELECT source_site FROM videos WHERE id = ?",
        (row_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "vimeo"
    Config._instance = None


def test_init_database_normalizes_legacy_youtube_variant(tmp_path, monkeypatch):
    from config import Config
    from database import _connect, add_video, init_database

    db = tmp_path / "legacy-source-site.db"
    cfg = Config()
    monkeypatch.setattr(cfg, "db_path", db)
    monkeypatch.setattr(cfg, "data_dir", tmp_path)
    Config._instance = cfg
    init_database()

    conn = _connect()
    conn.execute(
        """
        INSERT INTO videos (url, video_id, title, source_site)
        VALUES (?, ?, ?, ?)
        """,
        ("https://youtu.be/abc", "abc", "Legacy", "Youtube"),
    )
    conn.commit()
    conn.close()

    init_database()
    row_id = add_video(
        "https://www.youtube.com/watch?v=abc",
        video_id="abc",
        title="Canonical",
        source_site="youtube",
    )

    conn = _connect()
    rows = conn.execute(
        "SELECT id, source_site, title FROM videos WHERE video_id = ?",
        ("abc",),
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == row_id
    assert rows[0][1] == "youtube"
    assert rows[0][2] == "Canonical"
    Config._instance = None
