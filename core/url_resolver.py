"""Classify and expand YouTube URLs (single video vs playlist).

Rules (YT-PLAYLIST-001):
- ``/playlist?list=`` → expand all entries to watch URLs
- ``/watch?v=ID&list=`` → by default keep **only** that video (list is context)
  unless ``expand_watch_list=True``
- bare ``/watch?v=ID`` or youtu.be/ID → single video
- Per-item download still uses yt-dlp ``noplaylist`` so each job is one video
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

UrlItem = Union[str, Tuple[Any, ...], List[Any]]

_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }
)


def _log(logger: Optional[Callable[[str], None]], message: str) -> None:
    if logger:
        logger(message)


def is_youtube_url(url: str) -> bool:
    try:
        host = (urlparse(url.strip()).netloc or "").lower()
    except Exception:
        return False
    if host.startswith("www."):
        host = host[4:]
    return host in {h.replace("www.", "") for h in _YOUTUBE_HOSTS} or host in _YOUTUBE_HOSTS


def classify_youtube_url(url: str) -> str:
    """Return one of: single_video | playlist | video_with_playlist_context | other."""
    raw = (url or "").strip()
    if not raw:
        return "other"
    try:
        parsed = urlparse(raw)
    except Exception:
        return "other"

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    qs = parse_qs(parsed.query)

    if host not in ("youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"):
        return "other"

    if host == "youtu.be":
        vid = path.strip("/").split("/")[0] if path.strip("/") else ""
        if not vid:
            return "other"
        if "list" in qs:
            return "video_with_playlist_context"
        return "single_video"

    if "/playlist" in path:
        return "playlist"

    if path.startswith("/watch"):
        if "v" in qs and qs["v"]:
            if "list" in qs and qs["list"]:
                return "video_with_playlist_context"
            return "single_video"
        # watch without v but with list → treat as playlist page edge case
        if "list" in qs and qs["list"]:
            return "playlist"
        return "other"

    if path.startswith("/shorts/"):
        return "single_video"

    if path.startswith("/embed/"):
        return "single_video"

    return "other"


def canonicalize_watch_url(url: str) -> str:
    """Return a clean watch?v=ID URL when possible; strip list= and extra params."""
    raw = (url or "").strip()
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path or ""
    qs = parse_qs(parsed.query)

    video_id = None
    if host == "youtu.be":
        video_id = path.strip("/").split("/")[0] if path.strip("/") else None
    elif path.startswith("/watch") and qs.get("v"):
        video_id = qs["v"][0]
    elif path.startswith("/shorts/"):
        video_id = path.strip("/").split("/")[1] if "/" in path.strip("/") else path.split("/")[-1]
    elif path.startswith("/embed/"):
        video_id = path.strip("/").split("/")[1] if path.count("/") >= 2 else None

    if not video_id:
        return raw

    return f"https://www.youtube.com/watch?v={video_id}"


def playlist_page_url(url: str) -> str:
    """If URL has list=, build canonical playlist URL for expansion."""
    try:
        parsed = urlparse(url.strip())
        qs = parse_qs(parsed.query)
        list_id = (qs.get("list") or [None])[0]
        if list_id:
            return f"https://www.youtube.com/playlist?list={list_id}"
    except Exception:
        pass
    return url.strip()


def expand_playlist_entries(
    url: str,
    *,
    cookies_path: Optional[str] = None,
    logger: Optional[Callable[[str], None]] = None,
    ydl_factory: Optional[Callable[..., Any]] = None,
) -> List[str]:
    """Expand a playlist URL into watch?v= URLs via yt-dlp flat extract.

    ``ydl_factory`` is injectable for tests: callable returning a context manager
    with ``extract_info(url, download=False)``.
    """
    import yt_dlp

    ydl_opts: dict[str, Any] = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
    }
    if cookies_path and Path(cookies_path).exists():
        ydl_opts["cookiefile"] = str(cookies_path)

    factory = ydl_factory or (lambda opts: yt_dlp.YoutubeDL(opts))

    try:
        with factory(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        _log(logger, f"❌ Falha ao expandir playlist: {exc}")
        return []

    if not info:
        return []

    entries = info.get("entries")
    if entries is None:
        # Not a playlist — single entry
        vid = info.get("id")
        if vid:
            return [f"https://www.youtube.com/watch?v={vid}"]
        webpage = info.get("webpage_url") or info.get("original_url")
        return [webpage] if webpage else [url]

    out: List[str] = []
    seen = set()
    for entry in entries:
        if not entry:
            continue
        watch = None
        if entry.get("url") and str(entry["url"]).startswith("http"):
            # flat entries sometimes give full URL or just id
            u = str(entry["url"])
            if "watch" in u or "youtu.be" in u:
                watch = canonicalize_watch_url(u)
            elif re.fullmatch(r"[\w-]{6,}", u):
                watch = f"https://www.youtube.com/watch?v={u}"
        if not watch and entry.get("id"):
            watch = f"https://www.youtube.com/watch?v={entry['id']}"
        if not watch and entry.get("webpage_url"):
            watch = canonicalize_watch_url(str(entry["webpage_url"]))
        if watch and watch not in seen:
            seen.add(watch)
            out.append(watch)

    _log(logger, f"📋 Playlist expandida: {len(out)} vídeo(s)")
    return out


def _unpack_item(item: UrlItem) -> Tuple[Any, str, Any]:
    if isinstance(item, (tuple, list)):
        queue_id = item[0] if len(item) >= 1 else None
        url = str(item[1]) if len(item) >= 2 else ""
        item_type = item[2] if len(item) >= 3 else None
        return queue_id, url, item_type
    return None, str(item), None


def _pack_item(queue_id: Any, url: str, item_type: Any, *, as_tuple: bool) -> UrlItem:
    if as_tuple:
        return (queue_id, url, item_type)
    return url


def expand_input_urls(
    items: Sequence[UrlItem],
    *,
    expand_watch_list: bool = False,
    cookies_path: Optional[str] = None,
    logger: Optional[Callable[[str], None]] = None,
    ydl_factory: Optional[Callable[..., Any]] = None,
) -> List[UrlItem]:
    """Expand mixed inputs into a flat list of processable URLs / queue tuples.

    - Playlist page → N watch URLs (queue_id cleared for expanded children)
    - watch?v=&list= → 1 canonical watch URL unless expand_watch_list
    - single video → 1 canonical watch URL
    - local / other → unchanged
    """
    result: List[UrlItem] = []

    for item in items:
        as_tuple = isinstance(item, (tuple, list))
        queue_id, url, item_type = _unpack_item(item)
        url = (url or "").strip()
        if not url:
            continue

        # Local files / non-youtube: pass through
        if item_type == "local":
            result.append(_pack_item(queue_id, url, item_type, as_tuple=as_tuple))
            continue
        if Path(url).expanduser().exists() and not url.startswith("http"):
            result.append(_pack_item(queue_id, url, item_type or "local", as_tuple=as_tuple))
            continue
        if not is_youtube_url(url):
            result.append(_pack_item(queue_id, url, item_type, as_tuple=as_tuple))
            continue

        kind = classify_youtube_url(url)

        if kind == "playlist":
            entries = expand_playlist_entries(
                url, cookies_path=cookies_path, logger=logger, ydl_factory=ydl_factory
            )
            if not entries:
                _log(logger, "⚠️ Playlist sem entradas; mantendo URL original")
                result.append(_pack_item(queue_id, url, item_type, as_tuple=as_tuple))
                continue
            for i, watch in enumerate(entries):
                # Only first expanded item keeps original queue_id for status mapping
                qid = queue_id if i == 0 else None
                result.append(_pack_item(qid, watch, item_type, as_tuple=as_tuple))
            continue

        if kind == "video_with_playlist_context":
            if expand_watch_list:
                pl = playlist_page_url(url)
                entries = expand_playlist_entries(
                    pl, cookies_path=cookies_path, logger=logger, ydl_factory=ydl_factory
                )
                if entries:
                    for i, watch in enumerate(entries):
                        qid = queue_id if i == 0 else None
                        result.append(_pack_item(qid, watch, item_type, as_tuple=as_tuple))
                    continue
            # Default: only the video itself
            watch = canonicalize_watch_url(url)
            _log(logger, f"🎬 Vídeo com list= (contexto): processando só {watch}")
            result.append(_pack_item(queue_id, watch, item_type, as_tuple=as_tuple))
            continue

        if kind == "single_video":
            watch = canonicalize_watch_url(url)
            result.append(_pack_item(queue_id, watch, item_type, as_tuple=as_tuple))
            continue

        result.append(_pack_item(queue_id, url, item_type, as_tuple=as_tuple))

    return result


def count_expanded_videos(items: Sequence[UrlItem]) -> int:
    """Count resulting video-like URLs after expand (for UI messages)."""
    n = 0
    for item in items:
        _, url, item_type = _unpack_item(item)
        if item_type == "local":
            continue
        if is_youtube_url(url) or (url.startswith("http") and "youtu" in url):
            n += 1
        elif url.startswith("http"):
            n += 1
    return n
