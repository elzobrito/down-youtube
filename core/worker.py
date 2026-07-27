import os
import time
import hashlib
import urllib.parse
from pathlib import Path

from config import get_config
from database import (
    get_setting,
    get_latest_transcription_for_source,
    add_video,
    add_history,
    update_video_media,
    get_transcription_by_audio_hash,
    save_transcription,
)
from core.downloader import Downloader
from core.audio import AudioProcessor
from core.transcriber import Transcriber
from core.streaming_downloader import StreamingDownloader


class TranscriberWorker:
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

        # Core modules will be initialized lazily or with current settings in each process call
        # but we can also init them here if they don't hold state that changes per request (config changes need to be fetched)

    def cancelar(self):
        self.cancel_requested = True

    def processar_lista(self, urls, expand_watch_list=False):
        self.running = True
        self.cancel_requested = False

        # Expand playlists into individual watch URLs; keep noplaylist on each download
        from core.url_resolver import expand_input_urls

        cookies_path = None
        try:
            cfg0 = self._get_current_config()
            cookies_path = cfg0.get("cookies_path")
        except Exception:
            cookies_path = None

        original_count = len(urls)
        urls = expand_input_urls(
            urls,
            expand_watch_list=expand_watch_list,
            cookies_path=cookies_path,
            logger=self.log,
        )
        if len(urls) != original_count:
            self.log(
                f"📋 Entrada expandida: {original_count} item(ns) → {len(urls)} job(s) de vídeo"
            )

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
            
            # Use self._parse_local_path helper
            local_path = self._parse_local_path(url_str, item_type)
            
            if local_path:
                result = self.processar_arquivo_local(local_path)
            else:
                result = self.processar_url(url_str)

            if result == "success":
                sucesso += 1
                if queue_id is not None and self.queue_status:
                    self.queue_status(queue_id, "done")
            elif result == "skipped":
                pulado += 1
                if queue_id is not None and self.queue_status:
                    self.queue_status(queue_id, "skipped")
            else:
                falha += 1
                if queue_id is not None and self.queue_status:
                    self.queue_status(queue_id, "failed")

        self.log(f"\n{'=' * 50}")
        self.log(f"📊 RESUMO: ✅ {sucesso} sucesso | ❌ {falha} falha | ⏭️ {pulado} pulado")

        self.log(f"📊 RESUMO: ✅ {sucesso} sucesso | ❌ {falha} falha | ⏭️ {pulado} pulado")

        self._notify(
            "Processamento Concluido",
            f"Finalizado: {sucesso} sucesso, {falha} erro(s).",
            success=(falha == 0),
        )

        self.running = False
        if self.complete:
            self.complete()

        return {
            "success": sucesso,
            "failed": falha,
            "skipped": pulado,
            "cancelled": self.cancel_requested,
        }

    def _notify(self, title, message, success=True):
        """Envia notificação Windows Toast"""
        notifications_enabled = get_setting("notifications_enabled")
        self.log(f"📢 Notificação: enabled={notifications_enabled}")
        
        if notifications_enabled == "1":
            try:
                from integrations.notifications import notify_completion
                result = notify_completion(title, message, success)
                if result == True:
                    self.log(f"📢 Notificação enviada: {title}")
                elif result == False:
                    self.log("⚠️ Notificações de desktop indisponíveis (winotify/notify-send)")
                else:
                    self.log("⚠️ Erro ao enviar notificação (result=None)")
            except Exception as e:
                self.log(f"❌ Erro ao enviar notificacao: {e}")
        else:
            self.log("ℹ️ Notificações desabilitadas nas configurações")


    def processar_url(self, url):
        # 1. Check duplicates
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

        # 2. Setup
        cfg = self._get_current_config()
        output_dir = cfg["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        ffmpeg_path = cfg["ffmpeg_path"]
        cookies_path = cfg.get("cookies_path")

        self.log(f"\n{'=' * 50}")
        self.log(f"📥 Processando: {url}")

        start_time = time.perf_counter()
        
        # Initialize modules
        downloader = Downloader(progress_callback=self._update_progress, logger=self.log)
        audio_processor = AudioProcessor(ffmpeg_path=ffmpeg_path, logger=self.log, progress_callback=self._update_progress)
        
        self.progress("Iniciando download...")
        self.progress({"stage": "download", "percent": 0, "speed": "-", "eta": "-"})

        # 3. Download - Try streaming first if enabled, fallback to traditional
        arquivo_wav = None
        video_path = None
        info = None
        archive_audio = None  # high-quality audio archive (best quality + keep_audio)
        
        use_streaming = cfg.get("use_streaming_pipeline", False) and not cfg["keep_video"]
        
        # Notificar modo do pipeline
        if use_streaming:
            self.progress({"stage": "pipeline_mode", "mode": "streaming"})
        elif cfg["keep_video"]:
            self.progress({"stage": "pipeline_mode", "mode": "video"})
        else:
            self.progress({"stage": "pipeline_mode", "mode": "traditional"})
        
        if use_streaming:
            # STREAMING PIPELINE: Download + conversão simultâneos
            try:
                self.log("🚀 Usando pipeline de streaming (download + conversão paralelos)")
                streaming_dl = StreamingDownloader(
                    progress_callback=self._update_progress,
                    logger=self.log
                )
                arquivo_wav, info = streaming_dl.download_and_convert_streaming(
                    url,
                    output_dir,
                    ffmpeg_path,
                    cookies_path,
                    best_quality=cfg.get("audio_download_best_quality", False),
                )
                
                if not arquivo_wav:
                    # Fallback para modo tradicional
                    self.log("⚠️ Streaming falhou, tentando modo tradicional...")
                    use_streaming = False
                    
            except Exception as e:
                self.log(f"⚠️ Erro no streaming pipeline: {e}, usando modo tradicional")
                use_streaming = False
        
        # TRADITIONAL PIPELINE: Fallback ou quando keep_video=1
        if not use_streaming or not arquivo_wav:
            if cfg["keep_video"]:
                video_path, info = downloader.download_video(
                    url,
                    output_dir,
                    ffmpeg_path,
                    cookies_path=cookies_path,
                    best_quality=cfg.get("video_download_best_quality", False),
                )
                if not video_path:
                    return self._handle_failure(url, downloader.last_error, start_time)
                
                arquivo_wav = audio_processor.extract_audio(video_path, output_dir)
            else:
                arquivo_wav, info = downloader.download_audio(
                    url,
                    output_dir,
                    ffmpeg_path,
                    cookies_path=cookies_path,
                    best_quality=cfg.get("audio_download_best_quality", False),
                    keep_archive=cfg.get("keep_audio", False),
                )
                archive_audio = downloader.last_archive_audio_path

            if arquivo_wav and not cfg["keep_video"]:
                # Normalize if we just downloaded audio (already extracted by yt-dlp usually, but ensuring 16k mono)
                # Actually downloader ensures wav 16k, but normalizer double checks encoding
                arquivo_wav = audio_processor.normalize_audio(arquivo_wav, output_dir)

        if not arquivo_wav:
             # Fallback info usage
             return self._handle_failure(url, "Falha no download/extracao", start_time, info, video_path, cfg["keep_video"])

        # Atualizar NERD Panel com informações do sistema de arquivos
        if info:
            self.progress({
                "stage": "nerd_download",
                "format": info.get("format", "N/A"),
                "codec": info.get("acodec", "N/A"),
                "url": url[:80],
            })
            
            self.progress({
                "stage": "nerd_filesystem",
                "output_dir": output_dir,
                "video_id": info.get("id", "N/A"),
            })

        self.log(f"✅ Download: {info.get('title') if info else 'audio'}")
        
        # 4. Save Video Info
        video_db_id = add_video(
            url,
            video_id=(info or {}).get("id"),
            title=(info or {}).get("title"),
            channel=(info or {}).get("uploader") or (info or {}).get("channel"),
            duration=(info or {}).get("duration"),
            thumbnail_url=(info or {}).get("thumbnail"),
            audio_path=arquivo_wav if cfg["keep_audio"] else None,
            video_path=video_path if cfg["keep_video"] else None,
            source_site=Downloader.resolve_source_site(info, url),
        )
        
        if not cfg["keep_audio"]:
            update_video_media(video_db_id, audio_path=None, video_path=video_path if cfg["keep_video"] else None)

        # 5. Check duplicate video ID if URL was new
        if not existing_url:
            existing_video = get_latest_transcription_for_source(video_id=(info or {}).get("id"))
            if existing_video:
                if not self._confirm_duplicate(
                    "Transcricao existente",
                    "Ja existe transcricao para este video. Reprocessar?",
                ):
                    self.log("⏭️ Transcricao existente para video. Ignorado.")
                    self._cleanup(
                        arquivo_wav,
                        cfg["keep_audio"],
                        extra_paths=[archive_audio] if archive_audio else None,
                    )
                    add_history(
                        video_db_id,
                        "skipped_duplicate",
                        error_message="duplicado_video",
                        audio_path=arquivo_wav if cfg["keep_audio"] else None,
                        video_path=video_path if cfg["keep_video"] else None,
                        processing_time_seconds=time.perf_counter() - start_time,
                    )
                    return "skipped"

        # 6. Check Hash
        audio_hash = self._hash_file(arquivo_wav)
        existing_hash = get_transcription_by_audio_hash(audio_hash)
        if existing_hash:
            if not self._confirm_duplicate(
                "Audio ja transcrito",
                "Este audio ja foi transcrito. Reprocessar mesmo assim?",
            ):
                self.log("⏭️ Audio duplicado. Ignorado.")
                self._cleanup(
                    arquivo_wav,
                    cfg["keep_audio"],
                    extra_paths=[archive_audio] if archive_audio else None,
                )
                add_history(
                    video_db_id,
                    "skipped_duplicate",
                    error_message="duplicado_audio",
                    audio_path=arquivo_wav if cfg["keep_audio"] else None,
                    video_path=video_path if cfg["keep_video"] else None,
                    processing_time_seconds=time.perf_counter() - start_time,
                )
                return "skipped"

        # 7. Transcribe
        return self._run_transcription(
            arquivo_wav, output_dir, video_db_id, audio_hash, start_time, cfg,
            video_path=video_path if cfg["keep_video"] else None,
            archive_audio=archive_audio,
        )

    def processar_arquivo_local(self, file_path):
        # 1. Setup
        cfg = self._get_current_config()
        output_dir = cfg["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        ffmpeg_path = cfg["ffmpeg_path"]
        
        file_path = str(file_path)
        if not os.path.exists(file_path):
            self.log(f"❌ Arquivo local nao encontrado: {file_path}")
            video_db_id = add_video(file_path, title=Path(file_path).stem, source_site="local")
            add_history(video_db_id, "erro_transcricao", error_message="Arquivo nao encontrado", processing_time_seconds=0)
            return "failed"

        existing_url = get_latest_transcription_for_source(url=file_path)
        if existing_url:
            if not self._confirm_duplicate("Transcricao existente", "Ja existe transcricao. Reprocessar?"):
                self.log("⏭️ Ignorado.")
                video_db_id = add_video(file_path, title=Path(file_path).stem, source_site="local")
                add_history(video_db_id, "skipped_duplicate", error_message="duplicado_local", processing_time_seconds=0)
                return "skipped"

        self.log(f"\n{'=' * 50}")
        self.log(f"📥 Processando arquivo local: {file_path}")

        start_time = time.perf_counter()
        
        # Init modules
        audio_processor = AudioProcessor(ffmpeg_path=ffmpeg_path, logger=self.log, progress_callback=self._update_progress)
        
        # 2. Convert/Extract
        ext = Path(file_path).suffix.lower()
        is_video = ext in {".mp4", ".mkv", ".mov", ".webm", ".avi"}
        
        video_path = file_path if (is_video and cfg["keep_video"]) else None
        base_name = f"{Path(file_path).stem}_{int(start_time)}"
        
        audio_path = None
        if is_video:
            audio_path = audio_processor.convert_to_wav(file_path, output_dir, base_name, "Extraindo audio...")
        else:
            audio_path = audio_processor.convert_to_wav(file_path, output_dir, base_name, "Convertendo audio...")

        if not audio_path:
            video_db_id = add_video(file_path, title=Path(file_path).stem, source_site="local")
            add_history(video_db_id, "erro_transcricao", error_message="Falha conversao audio", processing_time_seconds=time.perf_counter() - start_time)
            return "failed"

        # 3. Save DB Info
        video_db_id = add_video(
            file_path,
            title=Path(file_path).stem,
            audio_path=audio_path if cfg["keep_audio"] else None,
            video_path=video_path,
            source_site="local",
        )
        if not cfg["keep_audio"]:
            update_video_media(video_db_id, audio_path=None, video_path=video_path)

        # 4. Hash Check
        audio_hash = self._hash_file(audio_path)
        existing_hash = get_transcription_by_audio_hash(audio_hash)
        if existing_hash:
             if not self._confirm_duplicate("Audio ja transcrito", "Reprocessar?"):
                 self.log("⏭️ Duplicado.")
                 self._cleanup(audio_path, cfg["keep_audio"])
                 add_history(video_db_id, "skipped_duplicate", error_message="duplicado_audio", audio_path=audio_path if cfg["keep_audio"] else None, video_path=video_path, processing_time_seconds=time.perf_counter()-start_time)
                 return "skipped"

        # 5. Transcribe
        return self._run_transcription(
            audio_path, output_dir, video_db_id, audio_hash, start_time, cfg,
            video_path=video_path
        )

    def _run_transcription(
        self,
        audio_path,
        output_dir,
        video_db_id,
        audio_hash,
        start_time,
        cfg,
        video_path=None,
        archive_audio=None,
    ):
        audio_processor = AudioProcessor(logger=self.log)
        duration = audio_processor.get_wav_duration(audio_path)
        
        # Enviar dados NERD de conversão
        self.progress({
            "stage": "nerd_conversion",
            "ffmpeg_command": "-ar 16000 -ac 1 -c:a pcm_s16le",
            "sample_rate": "48000 Hz → 16000 Hz",
            "channels": "stereo → mono",
            "output_bitrate": "256 kbps (16-bit PCM)"
        })
        
        transcriber = Transcriber(
            cli_path=cfg["whisper_cli"],
            model_path=cfg["whisper_model"],
            language=cfg["whisper_language"],
            threads=cfg["whisper_threads"],
            beam_size=cfg["whisper_beam_size"],
            best_of=cfg["whisper_best_of"],
            use_gpu=cfg["whisper_use_gpu"],
            logger=self.log,
            progress_callback=self._update_progress,
            cancel_check_callback=lambda: self.cancel_requested,
            long_audio_threshold_seconds=cfg.get(
                "whisper_long_audio_threshold_seconds", 3600
            ),
            chunk_seconds=cfg.get("whisper_chunk_seconds", 1800),
            ffmpeg_path=cfg.get("ffmpeg_path") or "ffmpeg",
        )
        
        # Enviar dados NERD de transcrição
        model_name = os.path.basename(cfg["whisper_model"]) if cfg["whisper_model"] else "default"
        self.progress({
            "stage": "nerd_transcription",
            "model": model_name,
            "backend": "whisper.cpp",
            "language_prob": f"{cfg['whisper_language']}",
            "speed": "calculating..."
        })

        arquivo_txt = transcriber.transcribe(audio_path, output_dir, duration=duration)
        elapsed = time.perf_counter() - start_time
        
        # Atualizar NERD com velocidade real
        if duration and duration > 0:
            speed = duration / elapsed if elapsed > 0 else 0
            self.progress({
                "stage": "nerd_transcription",
                "model": model_name,
                "backend": "whisper.cpp",
                "language_prob": f"{cfg['whisper_language']}",
                "speed": f"{speed:.2f}x realtime",
                "processing_time": f"{elapsed:.1f}s"
            })

        if arquivo_txt:
            self.log(f"✅ Transcricao salva: {arquivo_txt}")
            text = ""

            try:
                with open(arquivo_txt, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except Exception as e:
                self.log(f"❌ Erro leitura: {e}")

            save_transcription(
                video_db_id,
                text,
                segments=transcriber.last_segments,
                language=cfg["whisper_language"],
                model=cfg["whisper_model"],
                audio_hash=audio_hash
            )
            add_history(
                video_db_id, "sucesso", output_file=arquivo_txt,
                audio_path=audio_path if cfg["keep_audio"] else None,
                video_path=video_path,
                processing_time_seconds=elapsed
            )
        else:
            self.log("❌ Falha na transcricao")
            add_history(
                video_db_id, "erro_transcricao", error_message=transcriber.last_error or "Erro desconhecido",
                audio_path=audio_path if cfg["keep_audio"] else None,
                video_path=video_path,
                processing_time_seconds=elapsed
            )

        self._cleanup(audio_path, cfg["keep_audio"], extra_paths=[archive_audio] if archive_audio else None)
        self.progress("Concluido")
        return "success" if arquivo_txt else "failed"

    def _cleanup(self, audio_path, keep_audio, extra_paths=None):
        if keep_audio:
            return
        paths = []
        if audio_path:
            paths.append(audio_path)
        for extra in extra_paths or []:
            if extra:
                paths.append(extra)
        for path in paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    self.log(f"🗑️ Audio removido: {os.path.basename(path)}")
            except Exception:
                pass

    def _handle_failure(self, url, error, start_time, info=None, video_path=None, keep_video=False):
        video_db_id = add_video(
            url,
            video_id=(info or {}).get("id"),
            title=(info or {}).get("title"),
            video_path=video_path if keep_video else None,
            source_site=Downloader.resolve_source_site(info, url),
        )
        add_history(
            video_db_id,
            "erro_download",
            error_message=error,
            processing_time_seconds=time.perf_counter() - start_time,
        )
        self.log("❌ Falha no download")
        return "failed"

    def _get_current_config(self):
        output_dir = get_setting("output_dir")
        if not output_dir:
            output_dir = str(Path.home() / "Downloads" / "Transcricoes")
        else:
            output_dir = str(output_dir)

        # Get cookies path from settings (configured by user)
        cookies_path_setting = get_setting("cookies_path")
        cookies_path = None
        
        if cookies_path_setting:
            cookies_file = Path(cookies_path_setting)
            if cookies_file.exists():
                cookies_path = cookies_file
            else:
                self.log(f"⚠️ Arquivo de cookies não encontrado: {cookies_path_setting}")
        
        # Fallback: Check for cookies.txt in current working directory
        if not cookies_path:
            fallback_cookies = Path.cwd() / "cookies.txt"
            if fallback_cookies.exists():
                cookies_path = fallback_cookies

        return {
            "ffmpeg_path": get_setting("ffmpeg_path"),
            "whisper_cli": get_setting("whisper_cli"),
            "whisper_model": get_setting("whisper_model"),
            "whisper_language": get_setting("whisper_language") or "pt",
            "output_dir": output_dir,
            "keep_audio": get_setting("keep_audio") == "1",
            "keep_video": get_setting("keep_video") == "1",
            "video_download_best_quality": get_setting("video_download_best_quality") == "1",
            "audio_download_best_quality": get_setting("audio_download_best_quality") == "1",
            "whisper_threads": self._get_int_setting("whisper_threads", 0),
            "whisper_beam_size": self._get_int_setting("whisper_beam_size", 1),
            "whisper_best_of": self._get_int_setting("whisper_best_of", 1),
            "whisper_use_gpu": get_setting("whisper_use_gpu") == "1",
            "whisper_long_audio_threshold_seconds": self._get_int_setting(
                "whisper_long_audio_threshold_seconds", 3600
            ),
            "whisper_chunk_seconds": self._get_int_setting("whisper_chunk_seconds", 1800),
            "use_streaming_pipeline": get_setting("use_streaming_pipeline") == "1",
            "cookies_path": str(cookies_path) if cookies_path else None,
        }

    def _get_int_setting(self, key, default):
        try:
            val = get_setting(key)
            return int(str(val).strip())
        except:
            return default

    def _confirm_duplicate(self, title, message):
         if not self.confirm:
             return False
         return self.confirm(title, message)

    def _update_progress(self, message):
        if self.progress:
            self.progress(message)

    @staticmethod
    def _hash_file(path, chunk_size=1024 * 1024):
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                while True:
                    chunk = handle.read(chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except:
             return None

    def _parse_local_path(self, value, item_type=None):
        candidate = value
        if candidate.startswith("file://"):
            candidate = candidate[7:]
            if candidate.startswith("/") and len(candidate) > 2 and candidate[2] == ":":
                candidate = candidate[1:]

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
