import os
import time
from pathlib import Path
from typing import Any, cast

import yt_dlp


class Downloader:
    def __init__(self, progress_callback=None, max_retries=3, ffmpeg_path=None):
        self.progress_callback = progress_callback
        self.max_retries = max_retries
        self.ffmpeg_path = ffmpeg_path

    def get_playlist_info(self, url):
        ydl_opts = cast(Any, {
            "quiet": True,
            "extract_flat": True,
            "force_generic_extractor": False,
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            info_dict = cast(Any, info)
            if "entries" in info_dict:
                return {
                    "type": "playlist",
                    "title": info_dict.get("title"),
                    "count": len(info_dict["entries"]),
                    "videos": [
                        {
                            "id": v.get("id"),
                            "title": v.get("title"),
                            "duration": v.get("duration"),
                            "url": v.get("url") or f"https://youtube.com/watch?v={v.get('id')}",
                        }
                        for v in info_dict["entries"]
                        if v
                    ],
                }

            return {
                "type": "video",
                "title": info_dict.get("title"),
                "videos": [info_dict],
            }

    def download_with_retry(self, url, output_dir, retry_count=0):
        try:
            return self._download(url, output_dir)
        except Exception as exc:
            if retry_count < self.max_retries:
                wait_time = (retry_count + 1) * 5
                time.sleep(wait_time)
                return self.download_with_retry(url, output_dir, retry_count + 1)
            raise exc

    def _download(self, url, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = cast(Any, {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "ffmpeg_location": self.ffmpeg_path,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._progress_hook],
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
            },
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"],
                }
            },
            "encoding": "utf-8",
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id") or info.get("display_id") or "audio"
            arquivo_wav = output_dir / f"{video_id}.wav"
            if arquivo_wav.exists():
                return str(arquivo_wav), info

            arquivos = list(output_dir.glob("*.wav"))
            if arquivos:
                arquivo_mais_recente = max(arquivos, key=os.path.getctime)
                return str(arquivo_mais_recente), info

        return None, None

    def _progress_hook(self, data):
        if not self.progress_callback:
            return
        if data.get("status") == "downloading":
            percent = data.get("_percent_str", "0%").strip()
            speed = data.get("_speed_str", "?").strip()
            eta = data.get("_eta_str", "?").strip()
            self.progress_callback(percent, speed, eta)
