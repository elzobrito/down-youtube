import os
import time
from pathlib import Path
from typing import Any, Optional, cast
from urllib.parse import urlparse
import yt_dlp

from core.url_resolver import is_youtube_url


# Compatible preset (legacy): favors MP4 merge for easy playback.
VIDEO_FORMAT_COMPAT = "bestvideo+bestaudio/best"
# Best-effort max quality: any codec pair, prefer pure best streams.
VIDEO_FORMAT_BEST = "bv*+ba/b"
VIDEO_CLIENTS_COMPAT = ["android", "web"]
# Prefer clients that often expose higher ladders before android-only sets.
VIDEO_CLIENTS_BEST = ["web", "web_safari", "tv", "android"]

# Audio-only presets
AUDIO_FORMAT_COMPAT = "bestaudio/best"
AUDIO_FORMAT_BEST = "ba/b"


class Downloader:
    def __init__(self, progress_callback=None, logger=None):
        self.progress_callback = progress_callback
        self.logger = logger
        self.last_error = None
        # High-quality archive path (m4a/opus/…) when best audio download keeps original
        self.last_archive_audio_path = None

    def _log(self, message):
        if self.logger:
            self.logger(message)

    @staticmethod
    def video_format_spec(best_quality=False):
        """
        Return yt-dlp format string for video downloads.

        best_quality=True  -> highest available video+audio (any codec).
        best_quality=False -> legacy compatible pair (typically MP4 merge).
        """
        return VIDEO_FORMAT_BEST if best_quality else VIDEO_FORMAT_COMPAT

    @staticmethod
    def video_merge_format(best_quality=False):
        """Best quality may need MKV to avoid forced re-encode of AV1/VP9 into MP4."""
        return "mkv" if best_quality else "mp4"

    @staticmethod
    def video_player_clients(best_quality=False):
        return list(VIDEO_CLIENTS_BEST if best_quality else VIDEO_CLIENTS_COMPAT)

    @staticmethod
    def audio_format_spec(best_quality=False):
        """bestaudio/best (compat) vs ba/b (prefer pure best audio stream)."""
        return AUDIO_FORMAT_BEST if best_quality else AUDIO_FORMAT_COMPAT

    @staticmethod
    def audio_player_clients(best_quality=False):
        return list(VIDEO_CLIENTS_BEST if best_quality else VIDEO_CLIENTS_COMPAT)

    @staticmethod
    def audio_format_sort(best_quality=False):
        """Prefer higher bitrate / sample rate when maximizing archive quality."""
        if best_quality:
            return ["abr", "asr"]
        return None

    @staticmethod
    def uses_youtube_extractor(url: str) -> bool:
        """True when yt-dlp should receive YouTube-only extractor_args."""
        return is_youtube_url(url or "")

    @staticmethod
    def youtube_extractor_args(url: str, clients: list) -> Optional[dict]:
        """
        Return extractor_args only for YouTube hosts.

        Non-YouTube sites (Vimeo, etc.) must not receive youtube:player_client.
        """
        if not Downloader.uses_youtube_extractor(url):
            return None
        return {"youtube": {"player_client": list(clients)}}

    @staticmethod
    def resolve_source_site(info: Optional[dict], url: str = "") -> str:
        """Prefer yt-dlp extractor_key; fall back to host or 'unknown' (not always youtube)."""
        if info:
            key = info.get("extractor_key") or info.get("extractor")
            if key:
                return str(key).lower()
        raw = (url or "").strip()
        if not raw:
            return "unknown"
        if is_youtube_url(raw):
            return "youtube"
        try:
            host = (urlparse(raw).netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                return host.split(":")[0]
        except Exception:
            pass
        return "unknown"

    def _common_http_headers(self):
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
        }

    def _format_download_error(self, url: str, exc: BaseException) -> str:
        msg = str(exc).strip() or type(exc).__name__
        if self.uses_youtube_extractor(url):
            return f"Erro no download (YouTube/yt-dlp): {msg}"
        return (
            f"Erro no download multi-site (yt-dlp): {msg}. "
            "Site pode não ser suportado, exigir cookies ou estar indisponível."
        )

    def download_audio(
        self,
        url,
        output_dir,
        ffmpeg_path=None,
        cookies_path=None,
        best_quality=False,
        keep_archive=False,
    ):
        """
        Download audio and produce a Whisper-ready WAV (16 kHz mono via later normalize).

        best_quality=True:
          - prefer ba/b + better YouTube clients + format_sort abr/asr
          - keep original high-quality file when keep_archive=True
          - convert a copy to WAV for transcription
        best_quality=False:
          - legacy bestaudio/best + extract to WAV (current behavior)
        """
        from core.audio import AudioProcessor

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.last_error = None
        self.last_archive_audio_path = None

        fmt = self.audio_format_spec(best_quality)
        clients = self.audio_player_clients(best_quality)
        sort = self.audio_format_sort(best_quality)
        yt_args = self.youtube_extractor_args(url, clients)

        ydl_opts = cast(Any, {
            "format": fmt,
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "ffmpeg_location": ffmpeg_path,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._progress_hook],
            "http_headers": self._common_http_headers(),
            "encoding": "utf-8",
        })
        if yt_args is not None:
            ydl_opts["extractor_args"] = yt_args
        if sort:
            ydl_opts["format_sort"] = sort

        if best_quality:
            site_note = (
                f"clients={','.join(clients)}"
                if yt_args is not None
                else "multi-site genérico (sem player_client YouTube)"
            )
            self._log(
                f"🎧 Download de áudio em máxima qualidade "
                f"(format={fmt}, {site_note}, keep_archive={keep_archive})"
            )
            # Keep original stream; convert to WAV ourselves for Whisper.
            ydl_opts["postprocessors"] = []
        else:
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ]

        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = str(cookies_path)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id") or info.get("display_id") or "audio"

                if not best_quality:
                    arquivo_wav = output_dir / f"{video_id}.wav"
                    if arquivo_wav.exists():
                        return str(arquivo_wav), info
                    arquivos = list(output_dir.glob("*.wav"))
                    if arquivos:
                        return str(max(arquivos, key=os.path.getctime)), info
                    return None, None

                # Best-quality path: locate original, convert to WAV, optional archive.
                source = self._find_downloaded_audio_source(output_dir, video_id)
                if not source:
                    self.last_error = "Arquivo de audio de alta qualidade nao encontrado apos download"
                    self._log(f"❌ {self.last_error}")
                    return None, None

                source_path = Path(source)
                # If yt-dlp already produced wav (rare), use it
                if source_path.suffix.lower() == ".wav":
                    wav_path = str(source_path)
                    if keep_archive:
                        self.last_archive_audio_path = wav_path
                    return wav_path, info

                audio_processor = AudioProcessor(
                    ffmpeg_path=ffmpeg_path or "ffmpeg",
                    logger=self.logger,
                    progress_callback=self.progress_callback,
                )
                wav_path = audio_processor.convert_to_wav(
                    str(source_path),
                    str(output_dir),
                    video_id,
                    status_message="Convertendo audio HQ para WAV (Whisper)...",
                )
                if not wav_path:
                    self.last_error = audio_processor.last_error or "Falha ao converter audio HQ para WAV"
                    self._log(f"❌ {self.last_error}")
                    return None, None

                if keep_archive:
                    self.last_archive_audio_path = str(source_path)
                    self._log(f"💾 Audio de alta qualidade preservado: {source_path.name}")
                else:
                    try:
                        if source_path.exists() and source_path.resolve() != Path(wav_path).resolve():
                            source_path.unlink()
                    except Exception:
                        pass

                return str(wav_path), info

        except Exception as exc:
            self.last_error = self._format_download_error(url, exc)
            self._log(f"❌ {self.last_error}")
            return None, None

    @staticmethod
    def _find_downloaded_audio_source(output_dir, video_id):
        output_dir = Path(output_dir)
        preferred = [".m4a", ".opus", ".webm", ".ogg", ".mp3", ".aac", ".flac", ".wav"]
        for ext in preferred:
            candidate = output_dir / f"{video_id}{ext}"
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        candidates = [
            p
            for p in output_dir.glob(f"{video_id}.*")
            if p.is_file() and p.suffix.lower() not in {".part", ".ytdl", ".json"}
        ]
        if candidates:
            return str(max(candidates, key=os.path.getctime))
        return None

    def download_video(
        self,
        url,
        output_dir,
        ffmpeg_path=None,
        cookies_path=None,
        best_quality=False,
    ):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        fmt = self.video_format_spec(best_quality)
        merge_fmt = self.video_merge_format(best_quality)
        clients = self.video_player_clients(best_quality)
        yt_args = self.youtube_extractor_args(url, clients)

        if best_quality:
            site_note = (
                f"clients={','.join(clients)}"
                if yt_args is not None
                else "multi-site genérico (sem player_client YouTube)"
            )
            self._log(
                f"📥 Download de vídeo em máxima qualidade "
                f"(format={fmt}, merge={merge_fmt}, {site_note})"
            )

        ydl_opts = cast(Any, {
            "format": fmt,
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "ffmpeg_location": ffmpeg_path,
            "merge_output_format": merge_fmt,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._progress_hook],
            "http_headers": self._common_http_headers(),
            "encoding": "utf-8",
        })
        if yt_args is not None:
            ydl_opts["extractor_args"] = yt_args

        if cookies_path and os.path.exists(cookies_path):
            ydl_opts["cookiefile"] = str(cookies_path)
            self._log(f"🍪 Usando arquivo de cookies: {os.path.basename(cookies_path)}")

        try:
            self.last_error = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id") or info.get("display_id") or "video"

                found = self._find_downloaded_video(output_dir, video_id)
                if found:
                    return found, info

            return None, None
        except Exception as exc:
            self.last_error = self._format_download_error(url, exc)
            self._log(f"❌ {self.last_error}")
            return None, None

    @staticmethod
    def _find_downloaded_video(output_dir, video_id):
        output_dir = Path(output_dir)
        # Prefer container expected for each mode, then any extension yt-dlp wrote.
        preferred = [".mp4", ".mkv", ".webm", ".mov", ".m4v"]
        for ext in preferred:
            candidate = output_dir / f"{video_id}{ext}"
            if candidate.exists():
                return str(candidate)

        candidates = list(output_dir.glob(f"{video_id}.*"))
        # Ignore audio-only intermediates if any remain
        audio_exts = {".m4a", ".webm", ".opus", ".ogg", ".mp3", ".wav", ".part"}
        video_like = [
            p
            for p in candidates
            if p.is_file() and p.suffix.lower() not in audio_exts
        ]
        if video_like:
            return str(max(video_like, key=os.path.getctime))
        if candidates:
            return str(max(candidates, key=os.path.getctime))
        return None

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

    def _parse_percent(self, value):
        try:
            return int(float(str(value).replace("%", "").strip()))
        except Exception:
            return 0
