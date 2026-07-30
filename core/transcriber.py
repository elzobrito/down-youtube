import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from core.audio import AudioProcessor


# Defaults aligned with config.DEFAULT_SETTINGS
DEFAULT_LONG_AUDIO_THRESHOLD_SECONDS = 600.0  # > 10 minutes
DEFAULT_CHUNK_SECONDS = 300.0  # 5-minute owned intervals
DEFAULT_CHUNK_OVERLAP_SECONDS = 5.0


class Transcriber:
    _cli_help_cache = {}

    def __init__(
        self,
        cli_path="whisper-cli",
        model_path="ggml-small.bin",
        language="portuguese",
        threads=0,
        beam_size=1,
        best_of=1,
        use_gpu=False,
        logger=None,
        progress_callback=None,
        cancel_check_callback=None,
        long_audio_threshold_seconds=DEFAULT_LONG_AUDIO_THRESHOLD_SECONDS,
        chunk_seconds=DEFAULT_CHUNK_SECONDS,
        chunk_overlap_seconds=DEFAULT_CHUNK_OVERLAP_SECONDS,
        prefer_silence_chunks=True,
        silence_search_seconds=15,
        vad_enabled=False,
        vad_model_path="",
        max_context=0,
        suppress_nst=True,
        ffmpeg_path="ffmpeg",
    ):
        self.cli_path = cli_path
        self.model_path = model_path
        self.language = language
        self.threads = threads
        self.beam_size = beam_size
        self.best_of = best_of
        self.use_gpu = use_gpu
        self.logger = logger
        self.progress_callback = progress_callback
        self.cancel_check = cancel_check_callback or (lambda: False)
        self.long_audio_threshold_seconds = float(long_audio_threshold_seconds)
        self.chunk_seconds = float(chunk_seconds)
        self.chunk_overlap_seconds = float(chunk_overlap_seconds)
        self.prefer_silence_chunks = bool(prefer_silence_chunks)
        self.silence_search_seconds = float(silence_search_seconds)
        self.vad_enabled = bool(vad_enabled)
        self.vad_model_path = str(vad_model_path or "").strip()
        self.max_context = int(max_context)
        self.suppress_nst = bool(suppress_nst)
        self.ffmpeg_path = ffmpeg_path
        self.last_error = None
        self.last_segments = None
        self.last_suppressed_repeat_segments = 0
        self._gpu_notice_logged = False

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def _progress(self, data):
        if self.progress_callback:
            self.progress_callback(data)

    def transcribe(self, audio_path, output_dir=None, duration=None):
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        output_dir = output_dir or str(Path(audio_path).parent)
        os.makedirs(output_dir, exist_ok=True)

        if duration is None:
            duration = AudioProcessor(ffmpeg_path=self.ffmpeg_path).get_wav_duration(audio_path)

        if AudioProcessor.should_chunk_duration(duration, self.long_audio_threshold_seconds):
            self._log(
                f"ℹ️ Áudio longo ({duration:.0f}s > {self.long_audio_threshold_seconds:.0f}s): "
                f"transcrição em pedaços de {self.chunk_seconds:.0f}s "
                f"com {self.chunk_overlap_seconds:.0f}s de sobreposição."
            )
            return self._transcribe_chunked(audio_path, output_dir, duration)

        return self._transcribe_single(audio_path, output_dir, duration=duration)

    def _transcribe_chunked(self, audio_path, output_dir, duration):
        """Split long audio, transcribe each piece, merge TXT/SRT with time offsets."""
        self.last_error = None
        self.last_segments = None
        self.last_suppressed_repeat_segments = 0
        audio_processor = AudioProcessor(
            ffmpeg_path=self.ffmpeg_path,
            logger=self.logger,
            progress_callback=self.progress_callback,
        )
        temp_dir = tempfile.mkdtemp(prefix="yt_whisper_chunks_")
        chunk_paths = []
        try:
            if self.cancel_check():
                self.last_error = "Processamento cancelado"
                return None

            chunks = audio_processor.split_wav_into_chunks(
                audio_path,
                chunk_seconds=self.chunk_seconds,
                output_dir=temp_dir,
                prefix=Path(audio_path).stem + "_part",
                overlap_seconds=self.chunk_overlap_seconds,
                prefer_silence=self.prefer_silence_chunks,
                silence_search_seconds=self.silence_search_seconds,
            )
            if not chunks:
                self.last_error = "Falha ao fatiar audio longo"
                self._log(f"❌ {self.last_error}")
                return None

            chunk_paths = [c["path"] for c in chunks]
            n = len(chunks)
            self._log(
                f"ℹ️ {n} pedaço(s) de ~{self.chunk_seconds:.0f}s para Whisper; "
                f"overlap={self.chunk_overlap_seconds:.0f}s, "
                f"corte_em_silencio={'sim' if self.prefer_silence_chunks else 'não'}."
            )

            merged_segments = []
            fallback_text = ""
            wall_start = time.perf_counter()

            for chunk in chunks:
                if self.cancel_check():
                    self.last_error = "Processamento cancelado"
                    return None

                idx = chunk["index"]
                offset = float(chunk["start"])
                chunk_duration = float(chunk["length"])
                owned_start = float(chunk.get("owned_start", offset))
                self._progress(
                    {
                        "stage": "transcription",
                        "percent": int((idx / n) * 100),
                        "elapsed": self._format_elapsed(time.perf_counter() - wall_start),
                        "message": f"Pedaço {idx + 1}/{n}",
                    }
                )

                # Capture outer callback BEFORE wrapping. Calling self._progress from
                # the wrapper would re-enter the wrapper (infinite recursion).
                original_cb = self.progress_callback

                def _chunk_progress(data, _idx=idx, _n=n, _start=wall_start, _orig=original_cb):
                    if not isinstance(data, dict):
                        if _orig:
                            _orig(data)
                        return
                    local = data.get("percent") or 0
                    try:
                        local = float(local)
                    except (TypeError, ValueError):
                        local = 0
                    overall = int(((_idx + local / 100.0) / _n) * 100)
                    payload = dict(data)
                    payload["percent"] = min(99, max(0, overall))
                    payload["elapsed"] = self._format_elapsed(time.perf_counter() - _start)
                    payload["message"] = f"Pedaço {_idx + 1}/{_n}"
                    if _orig:
                        _orig(payload)

                self.progress_callback = _chunk_progress
                try:
                    txt_path = self._transcribe_single(
                        chunk["path"],
                        output_dir=temp_dir,
                        duration=chunk_duration,
                        set_segments=False,
                    )
                finally:
                    self.progress_callback = original_cb

                if not txt_path or self.cancel_check():
                    if not self.last_error:
                        self.last_error = f"Falha na transcricao do pedaco {idx + 1}/{n}"
                    return None

                text = self._read_text(txt_path)

                srt_path = self._srt_path_for_txt(txt_path)
                if srt_path and srt_path.exists():
                    shifted = self._shift_srt_content(self._read_text(srt_path), offset)
                    merged_segments = self._merge_timestamped_segments(
                        merged_segments,
                        self._parse_srt(shifted) or [],
                        owned_start=owned_start,
                    )
                elif text:
                    # Fallback segment without fine timing
                    merged_segments = self._merge_timestamped_segments(
                        merged_segments,
                        [
                        {
                            "start": offset,
                            "end": offset + chunk_duration,
                            "text": text.strip(),
                        }
                        ],
                        owned_start=owned_start,
                    )
                if text:
                    fallback_text = self._merge_text_overlap(fallback_text, text.strip())

            if self.cancel_check():
                self.last_error = "Processamento cancelado"
                return None

            final_txt = self._final_txt_path(audio_path)
            final_srt = self._final_srt_path(audio_path)
            # Prefer writing beside the source audio (same as single-pass whisper layout)
            final_txt.parent.mkdir(parents=True, exist_ok=True)

            segment_text = "\n".join(
                str(segment.get("text") or "").strip()
                for segment in merged_segments
                if str(segment.get("text") or "").strip()
            )
            full_text = (segment_text or fallback_text).strip()
            if full_text:
                full_text += "\n"
            final_txt.write_text(full_text, encoding="utf-8")

            srt_body = self._segments_to_srt(merged_segments)
            final_srt.write_text(srt_body, encoding="utf-8")

            # Also place copies in output_dir when it differs from the audio folder
            out_dir = Path(output_dir)
            if out_dir.resolve() != final_txt.parent.resolve():
                out_txt = out_dir / final_txt.name
                out_srt = out_dir / final_srt.name
                out_txt.write_text(full_text, encoding="utf-8")
                out_srt.write_text(srt_body, encoding="utf-8")
                final_txt = out_txt

            self.last_segments = merged_segments or None
            if self.last_suppressed_repeat_segments:
                self._log(
                    "ℹ️ Proteção anti-loop removeu "
                    f"{self.last_suppressed_repeat_segments} segmento(s) repetido(s)."
                )
            self._progress(
                {
                    "stage": "transcription",
                    "percent": 100,
                    "elapsed": self._format_elapsed(time.perf_counter() - wall_start),
                    "message": f"{n} pedaços mesclados",
                }
            )
            self._log(f"✅ Transcrição longa mesclada: {final_txt}")
            return str(final_txt)
        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Erro na transcricao chunked: {exc}")
            return None
        finally:
            AudioProcessor.cleanup_chunk_artifacts(chunk_paths)
            try:
                # remove any leftover files in temp_dir then the dir
                for leftover in Path(temp_dir).glob("*"):
                    try:
                        leftover.unlink()
                    except Exception:
                        pass
                os.rmdir(temp_dir)
            except Exception:
                pass

    def _transcribe_single(self, audio_path, output_dir=None, duration=None, set_segments=True):
        """Run whisper-cli once on a single audio file. Returns path to .txt or None."""
        output_dir = output_dir or str(Path(audio_path).parent)
        os.makedirs(output_dir, exist_ok=True)

        comando = [
            self.cli_path,
            "-f",
            audio_path,
            "-l",
            self.language,
            "-m",
            self.model_path,
            "--output-txt",
            "--output-srt",
        ]

        if self.threads and self.threads > 0:
            comando.extend(["-t", str(self.threads)])
        else:
            comando.extend(["-t", str(os.cpu_count() or 1)])

        if self.beam_size and self.beam_size > 0:
            if self._cli_supports_option("--beam-size"):
                comando.extend(["--beam-size", str(self.beam_size)])
            elif self._cli_supports_option("-bs"):
                comando.extend(["-bs", str(self.beam_size)])

        if self.best_of and self.best_of > 0:
            if self._cli_supports_option("--best-of"):
                comando.extend(["--best-of", str(self.best_of)])
            elif self._cli_supports_option("-bo"):
                comando.extend(["-bo", str(self.best_of)])

        if self.max_context >= 0 and self._cli_supports_option("--max-context"):
            comando.extend(["--max-context", str(self.max_context)])

        if self.suppress_nst and self._cli_supports_option("--suppress-nst"):
            comando.append("--suppress-nst")

        if self.vad_enabled:
            if not self.vad_model_path or not Path(self.vad_model_path).is_file():
                self._log(
                    "⚠️ VAD solicitado, mas o modelo VAD não existe; "
                    "transcrição seguirá sem VAD."
                )
            elif self._cli_supports_option("--vad") and self._cli_supports_option(
                "--vad-model"
            ):
                comando.extend(["--vad", "--vad-model", self.vad_model_path])
                if self._cli_supports_option("--vad-max-speech-duration-s"):
                    comando.extend(["--vad-max-speech-duration-s", "30"])
                if self._cli_supports_option("--vad-samples-overlap"):
                    comando.extend(["--vad-samples-overlap", "0.20"])
            else:
                self._log("⚠️ whisper-cli atual não oferece VAD; opção ignorada.")

        if self.use_gpu and not self._gpu_notice_logged:
            self._log("ℹ️ GPU ativada: use um whisper-cli compilado com CUDA.")
            self._gpu_notice_logged = True

        try:
            self.last_error = None
            if set_segments:
                self.last_segments = None
            self._progress("Transcrevendo...")

            env = self._build_subprocess_env()

            error_path = self._create_temp_error_file()
            with open(error_path, "wb") as err_file:
                process = subprocess.Popen(
                    comando,
                    stdout=subprocess.DEVNULL,
                    stderr=err_file,
                    cwd=output_dir,
                    env=env,
                )

            start_time = time.perf_counter()

            while process.poll() is None:
                if self.cancel_check():
                    process.terminate()
                    self.last_error = "Processamento cancelado"
                    break

                elapsed = time.perf_counter() - start_time
                percent = self._estimate_percent(elapsed, duration)
                self._progress(
                    {
                        "stage": "transcription",
                        "percent": percent,
                        "elapsed": self._format_elapsed(elapsed),
                        "model": self.model_path or "",
                        "threads": self.threads or 0,
                    }
                )
                time.sleep(0.5)

            returncode = process.wait()
            stderr_output = self._read_error_file(error_path)

            if returncode == 0 and not self.cancel_check():
                self._progress(
                    {
                        "stage": "transcription",
                        "percent": 100,
                        "elapsed": self._format_elapsed(
                            time.perf_counter() - start_time
                        ),
                        "model": self.model_path or "",
                        "threads": self.threads or 0,
                    }
                )
                arquivo_txt = self._find_output_txt(audio_path, output_dir)
                if arquivo_txt:
                    if set_segments:
                        self.last_segments = self._load_segments_for(arquivo_txt)
                    return str(arquivo_txt)

                self._log_transcription_error(
                    "Arquivo de saida nao encontrado",
                    comando,
                    audio_path,
                    output_dir,
                    stderr_output,
                )
                return None

            if not self.cancel_check():
                self._log_transcription_error(
                    "Erro na transcricao",
                    comando,
                    audio_path,
                    output_dir,
                    stderr_output,
                )
            return None

        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Erro na transcricao: {exc}")
            return None

    def _find_output_txt(self, audio_path, output_dir):
        candidates = [
            Path(audio_path).with_suffix(".wav.txt") if Path(audio_path).suffix == ".wav" else None,
            Path(str(audio_path) + ".txt"),
            Path(audio_path).with_suffix(".txt"),
            Path(output_dir) / (Path(audio_path).name + ".txt"),
            Path(output_dir) / Path(audio_path).with_suffix(".wav.txt").name,
            Path(output_dir) / Path(audio_path).with_suffix(".txt").name,
        ]
        for candidate in candidates:
            if candidate is not None and candidate.exists():
                return candidate
        return None

    @staticmethod
    def _final_txt_path(audio_path):
        path = Path(audio_path)
        if path.suffix == ".wav":
            return Path(str(path) + ".txt")  # file.wav.txt
        return path.with_suffix(".txt")

    @staticmethod
    def _final_srt_path(audio_path):
        path = Path(audio_path)
        if path.suffix == ".wav":
            return Path(str(path) + ".srt")  # file.wav.srt
        return path.with_suffix(".srt")

    @staticmethod
    def _srt_path_for_txt(txt_path):
        txt_path = Path(txt_path)
        name = str(txt_path)
        if name.endswith(".txt"):
            return Path(name[:-4] + ".srt")
        return txt_path.with_suffix(".srt")

    @staticmethod
    def _read_text(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except Exception:
            return ""

    @staticmethod
    def _seconds_to_srt_time(seconds):
        if seconds is None or seconds < 0:
            seconds = 0.0
        total_ms = int(round(float(seconds) * 1000.0))
        hours, rem = divmod(total_ms, 3600 * 1000)
        minutes, rem = divmod(rem, 60 * 1000)
        secs, millis = divmod(rem, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @classmethod
    def _shift_srt_content(cls, content, offset_seconds):
        if not content or not content.strip():
            return ""
        offset = float(offset_seconds or 0.0)
        lines = content.replace("\r\n", "\n").split("\n")
        out = []
        time_re = re.compile(
            r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
        )
        for line in lines:
            match = time_re.match(line.strip())
            if match:
                start = cls._srt_time_to_seconds(match.group(1)) + offset
                end = cls._srt_time_to_seconds(match.group(2)) + offset
                out.append(
                    f"{cls._seconds_to_srt_time(start)} --> {cls._seconds_to_srt_time(end)}"
                )
            else:
                out.append(line)
        return "\n".join(out)

    @staticmethod
    def _renumber_srt_blocks(content, start_index=1):
        """Return (list_of_block_strings, next_index)."""
        blocks = []
        index = start_index
        raw = content.replace("\r\n", "\n").strip()
        if not raw:
            return blocks, index
        for block in raw.split("\n\n"):
            lines = [line for line in block.split("\n") if line.strip() != "" or True]
            # drop empty-only blocks
            nonempty = [line for line in block.split("\n") if line.strip()]
            if len(nonempty) < 2:
                continue
            timing_idx = 1 if len(nonempty) > 1 and "-->" in nonempty[1] else (
                0 if "-->" in nonempty[0] else -1
            )
            if timing_idx == -1:
                continue
            timing = nonempty[timing_idx]
            text_lines = nonempty[timing_idx + 1 :]
            if not text_lines:
                continue
            block_text = f"{index}\n{timing}\n" + "\n".join(text_lines)
            blocks.append(block_text)
            index += 1
        return blocks, index

    def _merge_timestamped_segments(self, existing, incoming, owned_start):
        """Merge a chunk while dropping timestamp/text duplicates in its overlap."""
        merged = [dict(segment) for segment in existing]
        boundary_limit = float(owned_start) + self.chunk_overlap_seconds + 2.0
        repeat_norm = ""
        repeat_count = 0
        repeat_end = -1.0
        for prior in reversed(merged):
            prior_norm = self._normalize_overlap_text(prior.get("text") or "")
            if not repeat_norm:
                repeat_norm = prior_norm
                repeat_end = float(prior.get("end") or prior.get("start") or 0.0)
                repeat_count = 1
            elif prior_norm == repeat_norm:
                repeat_count += 1
            else:
                break
        for raw_segment in incoming:
            segment = dict(raw_segment)
            start = float(segment.get("start") or 0.0)
            end = float(segment.get("end") or start)
            text = str(segment.get("text") or "").strip()
            midpoint = start + max(0.0, end - start) / 2.0
            if (
                not text
                or (
                    float(owned_start) > 0
                    and midpoint < float(owned_start) - 0.01
                )
            ):
                continue

            normalized = self._normalize_overlap_text(text)
            duplicate = False
            if float(owned_start) > 0 and start <= boundary_limit:
                for prior in reversed(merged[-8:]):
                    prior_text = self._normalize_overlap_text(prior.get("text") or "")
                    if normalized != prior_text:
                        continue
                    prior_start = float(prior.get("start") or 0.0)
                    prior_end = float(prior.get("end") or prior_start)
                    if start <= prior_end + 2.0 and end >= prior_start - 2.0:
                        duplicate = True
                        break
            if not duplicate:
                if normalized and normalized == repeat_norm and start <= repeat_end + 2.0:
                    repeat_count += 1
                    repeat_end = max(repeat_end, end)
                else:
                    repeat_norm = normalized
                    repeat_count = 1
                    repeat_end = end
                if repeat_count > 2:
                    duplicate = True
                    self.last_suppressed_repeat_segments += 1
            if not duplicate:
                segment["start"] = start
                segment["end"] = max(start, end)
                segment["text"] = text
                merged.append(segment)
        merged.sort(key=lambda item: (float(item.get("start") or 0.0), float(item.get("end") or 0.0)))
        return merged

    @classmethod
    def _merge_text_overlap(cls, accumulated, next_text, max_words=80):
        """Fallback de-duplication for Whisper builds that do not emit SRT."""
        left = str(accumulated or "").strip()
        right = str(next_text or "").strip()
        if not left:
            return right
        if not right:
            return left
        left_words = left.split()
        right_words = right.split()
        limit = min(max_words, len(left_words), len(right_words))
        overlap = 0
        for size in range(limit, 0, -1):
            left_norm = [cls._normalize_overlap_text(word) for word in left_words[-size:]]
            right_norm = [cls._normalize_overlap_text(word) for word in right_words[:size]]
            if left_norm == right_norm:
                overlap = size
                break
        remainder = " ".join(right_words[overlap:]).strip()
        return f"{left}\n{remainder}".strip() if remainder else left

    @staticmethod
    def _normalize_overlap_text(text):
        return re.sub(r"[^\w]+", " ", str(text).casefold()).strip()

    @classmethod
    def _segments_to_srt(cls, segments):
        blocks = []
        for index, segment in enumerate(segments or [], start=1):
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            start = cls._seconds_to_srt_time(float(segment.get("start") or 0.0))
            end = cls._seconds_to_srt_time(float(segment.get("end") or 0.0))
            blocks.append(f"{index}\n{start} --> {end}\n{text}")
        return "\n\n".join(blocks).strip() + ("\n" if blocks else "")

    def _cli_supports_option(self, option):
        help_text = self._get_cli_help()
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
        return option in options

    def _get_cli_help(self):
        if self.cli_path in self._cli_help_cache:
            return self._cli_help_cache[self.cli_path]
        try:
            result = subprocess.run(
                [self.cli_path, "-h"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_subprocess_env(),
            )
            help_text = (result.stdout or "") + (result.stderr or "")
        except Exception:
            help_text = ""
        self._cli_help_cache[self.cli_path] = help_text
        return help_text

    def _build_subprocess_env(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        library_paths = []

        cli_dir = self._cli_directory()
        if cli_dir:
            library_paths.append(str(cli_dir))

        library_paths.extend(self._cuda_library_paths(env))

        current = env.get("LD_LIBRARY_PATH")
        if current:
            library_paths.extend(path for path in current.split(os.pathsep) if path)

        if library_paths:
            env["LD_LIBRARY_PATH"] = os.pathsep.join(dict.fromkeys(library_paths))

        return env

    @staticmethod
    def _cuda_library_paths(env):
        candidates = []

        for variable in ("CUDA_HOME", "CUDA_PATH"):
            cuda_root = env.get(variable)
            if cuda_root:
                candidates.append(Path(cuda_root).expanduser() / "lib64")

        candidates.extend(
            [
                Path("/usr/local/cuda/lib64"),
                Path.home() / ".local/cuda-12.4/lib64",
                Path.home() / ".local/cuda-toolkit-12.4/usr/lib/x86_64-linux-gnu",
            ]
        )

        return [str(path.resolve()) for path in candidates if path.exists()]

    def _cli_directory(self):
        if not self.cli_path:
            return None

        cli_path = Path(str(self.cli_path)).expanduser()
        if cli_path.parent == Path("."):
            return None
        return cli_path.resolve().parent

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
        self.last_error = stderr_text

        self._log(f"❌ Erro Whisper: {stderr_text}")
        self._log(f"ℹ️ {summary}")
        self._log(f"ℹ️ Comando: {command_str}")
        self._log(f"ℹ️ Audio: {audio_path}")
        self._log(f"ℹ️ Diretório: {diretorio_saida}")

    @staticmethod
    def _load_segments_for(txt_path):
        srt_path = (
            Path(str(txt_path)[:-4] + ".srt")
            if str(txt_path).endswith(".txt")
            else Path(txt_path).with_suffix(".srt")
        )
        if not srt_path.exists():
            return None
        try:
            with open(srt_path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except Exception:
            return None
        return Transcriber._parse_srt(content)

    @staticmethod
    def _parse_srt(content):
        segments = []
        for block in content.replace("\r\n", "\n").strip().split("\n\n"):
            lines = [line for line in block.split("\n") if line.strip()]
            if len(lines) < 2:
                continue
            timing_idx = 1 if "-->" in lines[1] else (0 if "-->" in lines[0] else -1)
            if timing_idx == -1:
                continue
            try:
                start_str, end_str = [part.strip() for part in lines[timing_idx].split("-->")]
            except ValueError:
                continue
            text = " ".join(lines[timing_idx + 1 :]).strip()
            segments.append(
                {
                    "start": Transcriber._srt_time_to_seconds(start_str),
                    "end": Transcriber._srt_time_to_seconds(end_str),
                    "text": text,
                }
            )
        return segments or None

    @staticmethod
    def _srt_time_to_seconds(timestamp):
        try:
            hms, _, millis = timestamp.partition(",")
            if not millis:
                hms, _, millis = timestamp.partition(".")
            hours, minutes, seconds = hms.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis or 0) / 1000.0
        except Exception:
            return 0.0

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
