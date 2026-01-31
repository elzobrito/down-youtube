import os
import time
from pathlib import Path
from typing import Any, cast
import yt_dlp

class Downloader:
    def __init__(self, progress_callback=None, logger=None):
        self.progress_callback = progress_callback
        self.logger = logger
        self.last_error = None

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def download_audio(self, url, output_dir, ffmpeg_path=None, cookies_path=None):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = cast(Any, {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "ffmpeg_location": ffmpeg_path,
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

        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = str(cookies_path)

        try:
            self.last_error = None
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

        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Erro no download: {exc}")
            return None, None

    def download_video(self, url, output_dir, ffmpeg_path=None, cookies_path=None):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = cast(Any, {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "ffmpeg_location": ffmpeg_path,
            "merge_output_format": "mp4",
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

        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = str(cookies_path)
            self._log(f"🍪 Usando arquivo de cookies: {os.path.basename(cookies_path)}")

        try:
            self.last_error = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id") or info.get("display_id") or "video"

                expected_mp4 = output_dir / f"{video_id}.mp4"
                if expected_mp4.exists():
                    return str(expected_mp4), info

                candidates = list(output_dir.glob(f"{video_id}.*"))
                if candidates:
                    video_file = max(candidates, key=os.path.getctime)
                    return str(video_file), info

            return None, None
        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Erro no download: {exc}")
            return None, None

    def _progress_hook(self, d):
        if not self.progress_callback:
            return

        status = d.get("status")
        if status == "downloading":
            percent_raw = d.get("_percent_str", "0%").strip()
            speed = d.get("_speed_str", "-").strip()
            eta = d.get("_eta_str", "-").strip()
            percent = self._parse_percent(percent_raw)
            self.progress_callback(
                {
                    "stage": "download",
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                }
            )
        elif status == "finished":
            self.progress_callback(
                {
                    "stage": "download",
                    "percent": 100,
                    "speed": "-",
                    "eta": "0s",
                }
            )
            # Optional: signal conversion start if needed
            # self.progress_callback("Convertendo para WAV...")

    def _parse_percent(self, value):
        try:
            return int(float(str(value).replace("%", "").strip()))
        except Exception:
            return 0
