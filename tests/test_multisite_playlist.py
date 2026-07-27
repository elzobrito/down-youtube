"""Generic multi-site playlist/set expansion (YT-MULTISITE-002)."""

from __future__ import annotations

from core.url_resolver import (
    expand_generic_entries,
    expand_input_urls,
    expand_playlist_entries,
    is_http_url,
)


VIMEO_SHOWCASE = "https://vimeo.com/showcase/12345"
VIMEO_SINGLE = "https://vimeo.com/987654321"
YT_PLAYLIST = "https://www.youtube.com/playlist?list=PLtest"


class _FakeYDL:
    def __init__(self, info):
        self._info = info

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        return self._info


def test_is_http_url():
    assert is_http_url("https://vimeo.com/1") is True
    assert is_http_url("http://example.com/a") is True
    assert is_http_url("/local/path.mp4") is False
    assert is_http_url("") is False


def test_expand_generic_multi_entries():
    def factory(_opts):
        return _FakeYDL(
            {
                "_type": "playlist",
                "entries": [
                    {"webpage_url": "https://vimeo.com/111"},
                    {"url": "https://vimeo.com/222"},
                    {"webpage_url": "https://vimeo.com/333"},
                ],
            }
        )

    out = expand_generic_entries(VIMEO_SHOWCASE, ydl_factory=factory)
    assert out == [
        "https://vimeo.com/111",
        "https://vimeo.com/222",
        "https://vimeo.com/333",
    ]


def test_expand_generic_single_keeps_original():
    def factory(_opts):
        return _FakeYDL(
            {
                "id": "987654321",
                "webpage_url": VIMEO_SINGLE,
                # no entries → single
            }
        )

    out = expand_generic_entries(VIMEO_SINGLE, ydl_factory=factory)
    assert out == [VIMEO_SINGLE]


def test_expand_generic_one_entry_keeps_original():
    def factory(_opts):
        return _FakeYDL(
            {
                "entries": [
                    {"webpage_url": "https://vimeo.com/only-one"},
                ],
            }
        )

    out = expand_generic_entries(VIMEO_SINGLE, ydl_factory=factory)
    assert out == [VIMEO_SINGLE]


def test_expand_generic_failure_keeps_original():
    class Boom:
        def __init__(self, _opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            raise RuntimeError("network down")

    out = expand_generic_entries(VIMEO_SINGLE, ydl_factory=Boom)
    assert out == [VIMEO_SINGLE]


def test_expand_input_urls_generic_playlist():
    def factory(_opts):
        return _FakeYDL(
            {
                "entries": [
                    {"webpage_url": "https://vimeo.com/a1"},
                    {"webpage_url": "https://vimeo.com/a2"},
                ],
            }
        )

    out = expand_input_urls([VIMEO_SHOWCASE], ydl_factory=factory)
    assert out == ["https://vimeo.com/a1", "https://vimeo.com/a2"]


def test_expand_input_urls_generic_single():
    def factory(_opts):
        return _FakeYDL({"id": "x", "title": "one"})

    out = expand_input_urls([VIMEO_SINGLE], ydl_factory=factory)
    assert out == [VIMEO_SINGLE]


def test_youtube_playlist_path_unchanged():
    """YouTube still uses expand_playlist_entries → watch?v= IDs."""

    def factory(_opts):
        return _FakeYDL(
            {
                "entries": [
                    {"id": "aaa111bbb22"},
                    {"id": "ccc222ddd33"},
                ],
            }
        )

    # Direct YouTube expander
    urls = expand_playlist_entries(YT_PLAYLIST, ydl_factory=factory)
    assert urls == [
        "https://www.youtube.com/watch?v=aaa111bbb22",
        "https://www.youtube.com/watch?v=ccc222ddd33",
    ]

    out = expand_input_urls([YT_PLAYLIST], ydl_factory=factory)
    assert out == urls
