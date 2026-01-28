"""
YouTube Transcriber - Interface Grafica
Ferramenta para download e transcricao de videos do YouTube
"""

import threading
import os
import sys
import subprocess
import time
import tempfile
import wave
import urllib.parse
import hashlib
from pathlib import Path
from typing import Any, cast

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import yt_dlp

from database import (
    init_database,
    get_setting,
    add_video,
    update_video_media,
    save_transcription,
    add_history,
    get_latest_transcription_for_source,
    get_transcription_by_audio_hash,
)

from gui.tabs.download_tab import DownloadTab
from gui.tabs.queue_tab import QueueTab
from gui.tabs.history_tab import HistoryTab
from gui.tabs.settings_tab import SettingsTab
from gui.tabs.library_tab import LibraryTab


class TranscriberWorker:
    _cli_help_cache = {}

    def __init__(
        self,
        log_callback,
        progress_callback,
        complete_callback,
        queue_status_callback=None,
        confirm_callback=None,
    ):
        self.log = log_callback
        self.progress = progress_callback
        self.complete = complete_callback
        self.queue_status = queue_status_callback
        self.confirm = confirm_callback
        self.running = False
        self.cancel_requested = False
        self.last_error = None
        self._gpu_notice_logged = False

    def baixar_audio(self, url, diretorio_saida):
        ffmpeg_path = get_setting("ffmpeg_path")

        ydl_opts = cast(Any, {
            "format": "bestaudio/best",
            "outtmpl": str(Path(diretorio_saida) / "%(id)s.%(ext)s"),
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

        try:
            self.last_error = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id") or info.get("display_id") or "audio"

                arquivo_wav = Path(diretorio_saida) / f"{video_id}.wav"
                if arquivo_wav.exists():
                    return str(arquivo_wav), info

                arquivos = list(Path(diretorio_saida).glob("*.wav"))
                if arquivos:
                    arquivo_mais_recente = max(arquivos, key=os.path.getctime)
                    return str(arquivo_mais_recente), info

            return None, None

        except Exception as exc:
            self.last_error = str(exc)
            self.log(f"❌ Erro no download: {exc}")
            return None, None

    def _progress_hook(self, d):
        status = d.get("status")
        if status == "downloading":
            percent_raw = d.get("_percent_str", "0%").strip()
            speed = d.get("_speed_str", "-").strip()
            eta = d.get("_eta_str", "-").strip()
            percent = self._parse_percent(percent_raw)
            self.progress(
                {
                    "stage": "download",
                    "percent": percent,
                    "speed": speed,
                    "eta": eta,
                }
            )
        elif status == "finished":
            self.progress(
                {
                    "stage": "download",
                    "percent": 100,
                    "speed": "-",
                    "eta": "0s",
                }
            )
            self.progress("Convertendo para WAV...")

    def transcrever_audio(self, arquivo_wav, diretorio_saida):
        whisper_cli = get_setting("whisper_cli")
        whisper_model = get_setting("whisper_model")
        whisper_language = get_setting("whisper_language")
        use_gpu = get_setting("whisper_use_gpu") == "1"

        if (not arquivo_wav) or (not os.path.exists(arquivo_wav)):
            self.last_error = f"Audio nao encontrado: {arquivo_wav}"
            self.log(f"❌ Audio nao encontrado: {arquivo_wav}")
            return None

        comando = [
            whisper_cli,
            "-f",
            arquivo_wav,
            "-l",
            whisper_language,
            "-m",
            whisper_model,
            "--output-txt",
        ]

        threads = self._get_int_setting("whisper_threads", 0)
        if threads <= 0:
            threads = os.cpu_count() or 1

        beam_size = self._get_int_setting("whisper_beam_size", 1)
        best_of = self._get_int_setting("whisper_best_of", 1)

        comando.extend(["-t", str(threads)])

        if beam_size > 0:
            if self._cli_supports_option(whisper_cli, "--beam-size"):
                comando.extend(["--beam-size", str(beam_size)])
            elif self._cli_supports_option(whisper_cli, "-bs"):
                comando.extend(["-bs", str(beam_size)])

        if best_of > 0:
            if self._cli_supports_option(whisper_cli, "--best-of"):
                comando.extend(["--best-of", str(best_of)])
            elif self._cli_supports_option(whisper_cli, "-bo"):
                comando.extend(["-bo", str(best_of)])

        if use_gpu and not self._gpu_notice_logged:
            self.log("ℹ️ GPU ativada: use um whisper-cli compilado com CUDA.")
            self._gpu_notice_logged = True

        try:
            self.last_error = None
            self.progress("Transcrevendo...")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            error_path = self._create_temp_error_file()
            with open(error_path, "wb") as err_file:
                process = subprocess.Popen(
                    comando,
                    stdout=subprocess.DEVNULL,
                    stderr=err_file,
                    cwd=diretorio_saida,
                    env=env,
                )

            duration = self._get_wav_duration(arquivo_wav)
            start_time = time.perf_counter()

            while process.poll() is None:
                if self.cancel_requested:
                    process.terminate()
                    self.last_error = "Processamento cancelado"
                    break

                elapsed = time.perf_counter() - start_time
                percent = self._estimate_percent(elapsed, duration)
                self.progress(
                    {
                        "stage": "transcription",
                        "percent": percent,
                        "elapsed": self._format_elapsed(elapsed),
                    }
                )
                time.sleep(0.5)

            returncode = process.wait()
            stderr_output = self._read_error_file(error_path)

            if returncode == 0 and not self.cancel_requested:
                self.progress(
                    {
                        "stage": "transcription",
                        "percent": 100,
                        "elapsed": self._format_elapsed(time.perf_counter() - start_time),
                    }
                )
                arquivo_txt = Path(arquivo_wav).with_suffix(".wav.txt")
                if arquivo_txt.exists():
                    return str(arquivo_txt)

                alternative_txt = Path(arquivo_wav).with_suffix(".txt")
                if alternative_txt.exists():
                    return str(alternative_txt)

                self._log_transcription_error(
                    "Arquivo de saida nao encontrado",
                    comando,
                    arquivo_wav,
                    diretorio_saida,
                    stderr_output,
                )
                return None

            if not self.cancel_requested:
                self._log_transcription_error(
                    "Erro na transcricao",
                    comando,
                    arquivo_wav,
                    diretorio_saida,
                    stderr_output,
                )
            return None

        except FileNotFoundError:
            self.last_error = f"Whisper nao encontrado: {whisper_cli}"
            self.log(f"❌ Whisper nao encontrado: {whisper_cli}")
            return None
        except Exception as exc:
            self.last_error = str(exc)
            self.log(f"❌ Erro na transcricao: {exc}")
            return None

    def baixar_video(self, url, diretorio_saida):
        ffmpeg_path = get_setting("ffmpeg_path")

        ydl_opts = cast(Any, {
            "format": "bestvideo+bestaudio/best",
            "outtmpl": str(Path(diretorio_saida) / "%(id)s.%(ext)s"),
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

        try:
            self.last_error = None
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info.get("id") or info.get("display_id") or "video"

                expected_mp4 = Path(diretorio_saida) / f"{video_id}.mp4"
                if expected_mp4.exists():
                    return str(expected_mp4), info

                candidates = list(Path(diretorio_saida).glob(f"{video_id}.*"))
                if candidates:
                    video_file = max(candidates, key=os.path.getctime)
                    return str(video_file), info

            return None, None
        except Exception as exc:
            self.last_error = str(exc)
            self.log(f"❌ Erro no download: {exc}")
            return None, None

    def extrair_audio(self, video_path, diretorio_saida):
        ffmpeg_path = get_setting("ffmpeg_path") or "ffmpeg"
        video_path = str(video_path)
        output_path = str(Path(diretorio_saida) / f"{Path(video_path).stem}.wav")

        command = [
            ffmpeg_path,
            "-y",
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            output_path,
        ]

        try:
            self.progress({"stage": "status", "message": "Extraindo audio..."})
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=diretorio_saida,
            )
            if result.returncode != 0:
                self.last_error = result.stderr
                self.log(f"❌ Erro ao extrair audio: {result.stderr}")
                return None
            return output_path if os.path.exists(output_path) else None
        except Exception as exc:
            self.last_error = str(exc)
            self.log(f"❌ Erro ao extrair audio: {exc}")
            return None

    def normalizar_audio(self, audio_path, diretorio_saida):
        ffmpeg_path = get_setting("ffmpeg_path") or "ffmpeg"
        audio_path = str(audio_path)
        temp_path = str(Path(audio_path).with_suffix(".norm.wav"))

        command = [
            ffmpeg_path,
            "-y",
            "-i",
            audio_path,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            temp_path,
        ]

        try:
            self.progress({"stage": "status", "message": "Normalizando audio..."})
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=diretorio_saida,
            )
            if result.returncode != 0:
                self.log(f"⚠️ Falha ao normalizar audio: {result.stderr}")
                return audio_path
            if os.path.exists(temp_path):
                os.replace(temp_path, audio_path)
            return audio_path
        except Exception as exc:
            self.log(f"⚠️ Falha ao normalizar audio: {exc}")
            return audio_path
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    def _convert_to_wav(self, input_path, diretorio_saida, base_name, status_message):
        ffmpeg_path = get_setting("ffmpeg_path") or "ffmpeg"
        output_path = str(Path(diretorio_saida) / f"{base_name}.wav")
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            output_path,
        ]
        try:
            self.progress({"stage": "status", "message": status_message})
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=diretorio_saida,
            )
            if result.returncode != 0:
                self.log(f"❌ Erro ao converter audio: {result.stderr}")
                return None
            return output_path if os.path.exists(output_path) else None
        except Exception as exc:
            self.log(f"❌ Erro ao converter audio: {exc}")
            return None

    def processar_url(self, url):
        if self.cancel_requested:
            return "failed"

        existing_url = get_latest_transcription_for_source(url=url)
        if existing_url:
            if not self._confirm_duplicate(
                "Transcricao existente",
                "Ja existe transcricao para esta URL. Reprocessar?",
            ):
                self.log("⏭️ Transcricao existente para URL. Ignorado.")
                video_db_id = add_video(url)
                add_history(
                    video_db_id,
                    "skipped_duplicate",
                    error_message="duplicado_url",
                    processing_time_seconds=0,
                )
                return "skipped"

        output_dir_setting = get_setting("output_dir")
        if output_dir_setting is None:
            diretorio = str(Path.home() / "Downloads" / "Transcricoes")
        else:
            diretorio = str(output_dir_setting)

        manter_audio = get_setting("keep_audio") == "1"
        manter_video = get_setting("keep_video") == "1"
        os.makedirs(diretorio, exist_ok=True)

        self.log(f"\n{'=' * 50}")
        self.log(f"📥 Processando: {url}")

        start_time = time.perf_counter()
        self.progress("Iniciando download...")
        self.progress({"stage": "download", "percent": 0, "speed": "-", "eta": "-"})

        arquivo_wav = None
        video_path = None
        info = None

        if manter_video:
            video_path, info = self.baixar_video(url, diretorio)
            if not video_path:
                video_db_id = add_video(url)
                elapsed = time.perf_counter() - start_time
                add_history(
                    video_db_id,
                    "erro_download",
                    error_message=self.last_error,
                    processing_time_seconds=elapsed,
                )
                self.log("❌ Falha no download")
                return "failed"
            arquivo_wav = self.extrair_audio(video_path, diretorio)
        else:
            arquivo_wav, info = self.baixar_audio(url, diretorio)

        if arquivo_wav and not manter_video:
            arquivo_wav = self.normalizar_audio(arquivo_wav, diretorio)

        if not arquivo_wav:
            video_db_id = add_video(
                url,
                video_id=(info or {}).get("id"),
                title=(info or {}).get("title"),
                channel=(info or {}).get("uploader") or (info or {}).get("channel"),
                duration=(info or {}).get("duration"),
                thumbnail_url=(info or {}).get("thumbnail"),
                audio_path=None,
                video_path=video_path if manter_video else None,
                source_site=((info or {}).get("extractor_key") or "youtube").lower(),
            )
            elapsed = time.perf_counter() - start_time
            add_history(
                video_db_id,
                "erro_download",
                error_message=self.last_error,
                audio_path=None,
                video_path=video_path if manter_video else None,
                processing_time_seconds=elapsed,
            )
            self.log("❌ Falha no download")
            return "failed"

        self.log(f"✅ Download: {info.get('title') if info else 'audio'}")

        video_db_id = add_video(
            url,
            video_id=(info or {}).get("id"),
            title=(info or {}).get("title"),
            channel=(info or {}).get("uploader") or (info or {}).get("channel"),
            duration=(info or {}).get("duration"),
            thumbnail_url=(info or {}).get("thumbnail"),
            audio_path=arquivo_wav if manter_audio else None,
            video_path=video_path if manter_video else None,
            source_site=((info or {}).get("extractor_key") or "youtube").lower(),
        )

        if not manter_audio:
            update_video_media(video_db_id, audio_path=None, video_path=video_path if manter_video else None)

        if not existing_url:
            existing_video = get_latest_transcription_for_source(video_id=(info or {}).get("id"))
            if existing_video:
                if not self._confirm_duplicate(
                    "Transcricao existente",
                    "Ja existe transcricao para este video. Reprocessar?",
                ):
                    self.log("⏭️ Transcricao existente para video. Ignorado.")
                    add_history(
                        video_db_id,
                        "skipped_duplicate",
                        error_message="duplicado_video",
                        audio_path=arquivo_wav if manter_audio else None,
                        video_path=video_path if manter_video else None,
                        processing_time_seconds=time.perf_counter() - start_time,
                    )
                    if not manter_audio and arquivo_wav and os.path.exists(arquivo_wav):
                        os.remove(arquivo_wav)
                    return "skipped"

        audio_hash = self._hash_file(arquivo_wav)
        existing_hash = get_transcription_by_audio_hash(audio_hash)
        if existing_hash:
            if not self._confirm_duplicate(
                "Audio ja transcrito",
                "Este audio ja foi transcrito. Reprocessar mesmo assim?",
            ):
                self.log("⏭️ Audio duplicado. Ignorado.")
                add_history(
                    video_db_id,
                    "skipped_duplicate",
                    error_message="duplicado_audio",
                    audio_path=arquivo_wav if manter_audio else None,
                    video_path=video_path if manter_video else None,
                    processing_time_seconds=time.perf_counter() - start_time,
                )
                if not manter_audio and arquivo_wav and os.path.exists(arquivo_wav):
                    os.remove(arquivo_wav)
                return "skipped"

        arquivo_txt = self.transcrever_audio(arquivo_wav, diretorio)
        elapsed = time.perf_counter() - start_time

        if arquivo_txt:
            self.log(f"✅ Transcricao salva: {arquivo_txt}")
            text_content = ""
            try:
                with open(arquivo_txt, "r", encoding="utf-8", errors="replace") as handle:
                    text_content = handle.read()
            except Exception as exc:
                self.log(f"❌ Erro ao ler transcricao: {exc}")

            save_transcription(
                video_db_id,
                text_content,
                segments=None,
                language=get_setting("whisper_language") or "pt",
                model=get_setting("whisper_model") or "small",
                audio_hash=audio_hash,
            )
            add_history(
                video_db_id,
                "sucesso",
                output_file=arquivo_txt,
                audio_path=arquivo_wav if manter_audio else None,
                video_path=video_path if manter_video else None,
                processing_time_seconds=elapsed,
            )
        else:
            self.log("❌ Falha na transcricao")
            add_history(
                video_db_id,
                "erro_transcricao",
                error_message=self.last_error,
                audio_path=arquivo_wav if manter_audio else None,
                video_path=video_path if manter_video else None,
                processing_time_seconds=elapsed,
            )

        if not manter_audio and arquivo_wav and os.path.exists(arquivo_wav):
            os.remove(arquivo_wav)
            self.log("🗑️ Audio removido")

        self.progress("Concluido")
        return "success" if arquivo_txt else "failed"

    def processar_arquivo_local(self, file_path):
        output_dir_setting = get_setting("output_dir")
        if output_dir_setting is None:
            diretorio = str(Path.home() / "Downloads" / "Transcricoes")
        else:
            diretorio = str(output_dir_setting)

        manter_audio = get_setting("keep_audio") == "1"
        manter_video = get_setting("keep_video") == "1"

        os.makedirs(diretorio, exist_ok=True)
        file_path = str(file_path)

        if not os.path.exists(file_path):
            self.last_error = "Arquivo local nao encontrado"
            self.log(f"❌ Arquivo local nao encontrado: {file_path}")
            video_db_id = add_video(
                file_path,
                title=Path(file_path).stem,
                source_site="local",
            )
            add_history(
                video_db_id,
                "erro_transcricao",
                error_message=self.last_error,
                processing_time_seconds=0,
            )
            return "failed"

        existing_url = get_latest_transcription_for_source(url=file_path)
        if existing_url:
            if not self._confirm_duplicate(
                "Transcricao existente",
                "Ja existe transcricao para este arquivo. Reprocessar?",
            ):
                self.log("⏭️ Transcricao existente para arquivo local. Ignorado.")
                video_db_id = add_video(
                    file_path,
                    title=Path(file_path).stem,
                    source_site="local",
                )
                add_history(
                    video_db_id,
                    "skipped_duplicate",
                    error_message="duplicado_local",
                    processing_time_seconds=0,
                )
                return "skipped"

        self.log(f"\n{'=' * 50}")
        self.log(f"📥 Processando arquivo local: {file_path}")

        start_time = time.perf_counter()
        ext = Path(file_path).suffix.lower()
        is_video = ext in {".mp4", ".mkv", ".mov", ".webm", ".avi"}

        audio_path = None
        video_path = file_path if (is_video and manter_video) else None

        base_name = f"{Path(file_path).stem}_{int(start_time)}"
        if is_video:
            audio_path = self._convert_to_wav(file_path, diretorio, base_name, "Extraindo audio...")
        else:
            audio_path = self._convert_to_wav(file_path, diretorio, base_name, "Convertendo audio...")

        if not audio_path:
            self.last_error = "Falha ao preparar audio"
            video_db_id = add_video(
                file_path,
                title=Path(file_path).stem,
                audio_path=None,
                video_path=video_path,
                source_site="local",
            )
            add_history(
                video_db_id,
                "erro_transcricao",
                error_message=self.last_error,
                audio_path=None,
                video_path=video_path,
                processing_time_seconds=time.perf_counter() - start_time,
            )
            return "failed"

        video_db_id = add_video(
            file_path,
            title=Path(file_path).stem,
            audio_path=audio_path if manter_audio else None,
            video_path=video_path,
            source_site="local",
        )

        if not manter_audio:
            update_video_media(video_db_id, audio_path=None, video_path=video_path)

        audio_hash = self._hash_file(audio_path)
        existing_hash = get_transcription_by_audio_hash(audio_hash)
        if existing_hash:
            if not self._confirm_duplicate(
                "Audio ja transcrito",
                "Este audio ja foi transcrito. Reprocessar mesmo assim?",
            ):
                self.log("⏭️ Audio duplicado. Ignorado.")
                add_history(
                    video_db_id,
                    "skipped_duplicate",
                    error_message="duplicado_audio",
                    audio_path=audio_path if manter_audio else None,
                    video_path=video_path,
                    processing_time_seconds=time.perf_counter() - start_time,
                )
                if not manter_audio and audio_path and os.path.exists(audio_path):
                    os.remove(audio_path)
                return "skipped"

        arquivo_txt = self.transcrever_audio(audio_path, diretorio)
        elapsed = time.perf_counter() - start_time

        if arquivo_txt:
            self.log(f"✅ Transcricao salva: {arquivo_txt}")
            text_content = ""
            try:
                with open(arquivo_txt, "r", encoding="utf-8", errors="replace") as handle:
                    text_content = handle.read()
            except Exception as exc:
                self.log(f"❌ Erro ao ler transcricao: {exc}")

            save_transcription(
                video_db_id,
                text_content,
                segments=None,
                language=get_setting("whisper_language") or "pt",
                model=get_setting("whisper_model") or "small",
                audio_hash=audio_hash,
            )
            add_history(
                video_db_id,
                "sucesso",
                output_file=arquivo_txt,
                audio_path=audio_path if manter_audio else None,
                video_path=video_path,
                processing_time_seconds=elapsed,
            )
        else:
            self.log("❌ Falha na transcricao")
            add_history(
                video_db_id,
                "erro_transcricao",
                error_message=self.last_error,
                audio_path=audio_path if manter_audio else None,
                video_path=video_path,
                processing_time_seconds=elapsed,
            )

        if not manter_audio and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
            self.log("🗑️ Audio removido")

        self.progress("Concluido")
        return "success" if arquivo_txt else "failed"

    def processar_lista(self, urls):
        self.running = True
        self.cancel_requested = False

        total = len(urls)
        sucesso = 0
        falha = 0
        pulado = 0

        for i, item in enumerate(urls, 1):
            if self.cancel_requested:
                self.log("\n⚠️ Processamento cancelado pelo usuario")
                break

            queue_id = None
            url = item
            item_type = None
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                queue_id = item[0]
                url = item[1]
                if len(item) >= 3:
                    item_type = item[2]

            if queue_id is not None and self.queue_status:
                self.queue_status(queue_id, "processing")

            self.log(f"\n[{i}/{total}]")
            url_str = str(url).strip()
            local_path = self._parse_local_path(url_str, item_type)
            if local_path:
                success = self.processar_arquivo_local(local_path)
            else:
                success = self.processar_url(url_str)

            if success == "success":
                sucesso += 1
                if queue_id is not None and self.queue_status:
                    self.queue_status(queue_id, "done")
            elif success == "skipped":
                pulado += 1
                if queue_id is not None and self.queue_status:
                    self.queue_status(queue_id, "skipped")
            else:
                falha += 1
                if queue_id is not None and self.queue_status:
                    self.queue_status(queue_id, "failed")

        self.log(f"\n{'=' * 50}")
        self.log(f"📊 RESUMO: ✅ {sucesso} sucesso | ❌ {falha} falha | ⏭️ {pulado} pulado")

        self.running = False
        self.complete()

    def cancelar(self):
        self.cancel_requested = True

    def _confirm_duplicate(self, title, message):
        if not self.confirm:
            return False
        return self.confirm(title, message)

    def _parse_local_path(self, value, item_type=None):
        candidate = value
        if candidate.startswith("file://"):
            candidate = self._strip_file_prefix(candidate)

        candidate = urllib.parse.unquote(candidate.strip().strip("\""))
        candidate_path = Path(candidate).expanduser()
        if not candidate_path.is_absolute():
            candidate_path = Path.cwd() / candidate_path
        candidate_path = candidate_path.resolve()

        if item_type == "local":
            return str(candidate_path)

        if os.path.exists(candidate_path):
            return str(candidate_path)
        return None

    @staticmethod
    def _strip_file_prefix(value):
        path = value
        if path.startswith("file://"):
            path = path[7:]
        if path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return path

    @staticmethod
    def _hash_file(path, chunk_size=1024 * 1024):
        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _parse_percent(value):
        try:
            return int(float(str(value).replace("%", "").strip()))
        except Exception:
            return 0

    @staticmethod
    def _get_int_setting(key, default):
        value = get_setting(key)
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def _cli_supports_option(self, cli_path, option):
        options = self._get_cli_options(cli_path)
        return option in options

    def _get_cli_help(self, cli_path):
        if cli_path in self._cli_help_cache:
            return self._cli_help_cache[cli_path]
        try:
            result = subprocess.run(
                [cli_path, "-h"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            help_text = (result.stdout or "") + (result.stderr or "")
        except Exception:
            help_text = ""
        self._cli_help_cache[cli_path] = help_text
        return help_text

    def _get_cli_options(self, cli_path):
        help_text = self._get_cli_help(cli_path)
        options = set()
        for line in help_text.splitlines():
            line = line.strip()
            if not line or not line.startswith("-"):
                continue
            head = line.split("[")[0].strip()
            parts = [part.strip() for part in head.split(",") if part.strip()]
            for part in parts:
                token = part.split()[0]
                if token.startswith("-"):
                    options.add(token)
        return options

    @staticmethod
    def _get_wav_duration(path):
        try:
            with wave.open(path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                if rate:
                    return frames / float(rate)
        except Exception:
            return None
        return None

    @staticmethod
    def _estimate_percent(elapsed, duration):
        if not duration:
            return 0
        percent = int((elapsed / duration) * 100)
        return min(99, max(0, percent))

    @staticmethod
    def _format_elapsed(seconds):
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _create_temp_error_file():
        handle, path = tempfile.mkstemp(prefix="whisper_err_", suffix=".log")
        os.close(handle)
        return path

    @staticmethod
    def _read_error_file(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read().strip()
        except Exception:
            return ""
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def _log_transcription_error(self, summary, comando, audio_path, diretorio_saida, stderr_output):
        stderr_text = stderr_output.strip() if stderr_output else "(sem detalhes no stderr)"
        command_str = " ".join(str(part) for part in comando)
        txt_files = self._list_txt_files(diretorio_saida)
        self.last_error = stderr_text

        self.log(f"❌ Erro Whisper: {stderr_text}")
        self.log(f"ℹ️ {summary}")
        self.log(f"ℹ️ Comando: {command_str}")
        self.log(f"ℹ️ Audio: {audio_path}")
        self.log(f"ℹ️ Diretório: {diretorio_saida}")
        if txt_files:
            self.log(f"ℹ️ Arquivos .txt encontrados: {', '.join(txt_files)}")
        else:
            self.log("ℹ️ Nenhum arquivo .txt encontrado no diretorio")

    @staticmethod
    def _list_txt_files(directory, max_items=10):
        try:
            files = sorted(Path(directory).glob("*.txt"), key=os.path.getctime, reverse=True)
            return [f.name for f in files[:max_items]]
        except Exception:
            return []


class YouTubeTranscriberApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Transcriber")
        self.root.geometry("800x600")
        self.root.minsize(700, 500)

        init_database()

        self.style = ttk.Style()
        theme = get_setting("theme")
        if theme in self.style.theme_names():
            self.style.theme_use(theme)

        self.worker = None
        self._create_menu()
        self._create_notebook()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Arquivo", menu=file_menu)
        file_menu.add_command(label="Importar Lista (.txt)", command=self._import_list)
        file_menu.add_command(label="Abrir Pasta de Saida", command=self._open_output_dir)
        file_menu.add_separator()
        file_menu.add_command(label="Sair", command=self._on_close)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ajuda", menu=help_menu)
        help_menu.add_command(label="Sobre", command=self._show_about)

    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.download_tab = DownloadTab(self.notebook, self)
        self.queue_tab = QueueTab(self.notebook, self)
        self.library_tab = LibraryTab(self.notebook, self)
        self.history_tab = HistoryTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self, self.style)

        self.tabs = {
            "download": self.download_tab,
            "queue": self.queue_tab,
            "library": self.library_tab,
            "history": self.history_tab,
            "settings": self.settings_tab,
        }

        self.notebook.add(self.download_tab, text="Download")
        self.notebook.add(self.queue_tab, text="Fila")
        self.notebook.add(self.library_tab, text="Biblioteca")
        self.notebook.add(self.history_tab, text="Historico")
        self.notebook.add(self.settings_tab, text="Configuracoes")

    def select_tab(self, name):
        tab = self.tabs.get(name)
        if tab:
            self.notebook.select(tab)

    def start_urls(self, urls):
        if self.worker and self.worker.running:
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)

        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete,
            None,
            self._confirm_action,
        )

        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=(urls,),
            daemon=True,
        )
        thread.start()

    def start_local_file(self, filepath):
        if self.worker and self.worker.running:
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)

        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete,
            None,
            self._confirm_action,
        )

        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=([(None, filepath, "local")],),
            daemon=True,
        )
        thread.start()

    def start_queue_items(self, items):
        if self.worker and self.worker.running:
            messagebox.showwarning("Aviso", "Ha um processamento em andamento.")
            return

        self.download_tab.set_processing(True)
        self.queue_tab.set_processing(True)

        self.worker = TranscriberWorker(
            self._log,
            self._update_progress,
            self._on_complete,
            self._update_queue_status,
            self._confirm_action,
        )

        thread = threading.Thread(
            target=self.worker.processar_lista,
            args=(items,),
            daemon=True,
        )
        thread.start()

    def cancel_process(self):
        if self.worker:
            self.worker.cancelar()
            self._log("⏳ Cancelando...")

    def _log(self, message):
        self.root.after(0, lambda: self.download_tab.log(message))

    def _update_progress(self, message):
        def apply_update():
            if isinstance(message, dict):
                stage = message.get("stage")
                if stage == "download":
                    self.download_tab.update_download_progress(
                        int(message.get("percent", 0)),
                        message.get("speed", "-"),
                        message.get("eta", "-"),
                    )
                elif stage == "transcription":
                    self.download_tab.update_transcription_progress(
                        int(message.get("percent", 0)),
                        message.get("elapsed", ""),
                    )
                elif stage == "status":
                    self.download_tab.update_progress(message.get("message", ""))
            else:
                self.download_tab.update_progress(message)

        self.root.after(0, apply_update)

    def _update_queue_status(self, queue_id, status):
        self.root.after(0, lambda: self.queue_tab.update_status(queue_id, status))

    def _confirm_action(self, title, message):
        result = {"value": False}
        done = threading.Event()

        def ask():
            result["value"] = messagebox.askyesno(title, message)
            done.set()

        self.root.after(0, ask)
        done.wait()
        return result["value"]

    def _on_complete(self):
        def apply_complete():
            self.download_tab.finish_progress()
            self.download_tab.set_processing(False)
            self.queue_tab.set_processing(False)
            self.history_tab.refresh()
            self.library_tab.refresh()

        self.root.after(0, apply_complete)

    def _import_list(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("Arquivo de Texto", "*.txt"), ("Todos", "*.*")]
        )

        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                lines = handle.readlines()

            count = 0
            for line in lines:
                url = line.strip()
                if url and not url.startswith("#"):
                    self.queue_tab.add_url(url)
                    count += 1

            self.select_tab("queue")
            messagebox.showinfo("Sucesso", f"{count} URLs importadas.")
        except Exception as exc:
            messagebox.showerror("Erro", f"Erro ao importar: {exc}")

    def _open_output_dir(self):
        output_dir_setting = get_setting("output_dir")
        if output_dir_setting is None:
            messagebox.showwarning("Aviso", "Pasta nao existe.")
            return

        output_dir = str(output_dir_setting)
        if os.path.exists(output_dir):
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", output_dir])
            else:
                subprocess.run(["xdg-open", output_dir])
        else:
            messagebox.showwarning("Aviso", "Pasta nao existe.")

    def _show_about(self):
        messagebox.showinfo(
            "Sobre",
            "YouTube Transcriber\n\n"
            "Versao 2.0 (base)\n\n"
            "Ferramenta para download e transcricao\n"
            "automatica de videos do YouTube.",
        )

    def _on_close(self):
        if self.worker and self.worker.running:
            if messagebox.askyesno(
                "Confirmar",
                "Ha um processamento em andamento.\nDeseja realmente sair?",
            ):
                self.worker.cancelar()
                self.root.destroy()
        else:
            self.root.destroy()


def run():
    root = tk.Tk()
    app = YouTubeTranscriberApp(root)
    root.mainloop()
