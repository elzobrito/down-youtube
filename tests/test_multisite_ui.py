"""UI helpers for multi-site clipboard / labels (YT-MULTISITE-003)."""

from pathlib import Path

from gui.tabs.download_tab import DownloadTab


def test_clipboard_accepts_any_http_url():
    assert DownloadTab.is_clipboard_media_url("https://vimeo.com/123456") is True
    assert DownloadTab.is_clipboard_media_url("https://soundcloud.com/a/b") is True
    assert DownloadTab.is_clipboard_media_url(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    ) is True
    assert DownloadTab.is_clipboard_media_url("https://youtu.be/dQw4w9WgXcQ") is True


def test_clipboard_rejects_non_urls():
    assert DownloadTab.is_clipboard_media_url("") is False
    assert DownloadTab.is_clipboard_media_url("not a url") is False
    assert DownloadTab.is_clipboard_media_url("/tmp/local.mp4") is False
    assert DownloadTab.is_clipboard_media_url("ftp://example.com/x") is False


def test_readme_documents_multisite_and_drm_limits():
    readme = Path(__file__).resolve().parents[1] / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert "Multi-site support" in text
    assert "best-effort" in text.lower()
    assert "DRM" in text
    assert "Vimeo" in text
    assert "YouTube" in text
    # Must not claim universal arbitrary download of protected services
    assert "Netflix" in text
