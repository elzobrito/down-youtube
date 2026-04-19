import os
import subprocess
import time
import tempfile
from pathlib import Path

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
        cancel_check_callback=None
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
        self.last_error = None
        self.last_segments = None
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
            # Default to CPU count if 0
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

        if self.use_gpu and not self._gpu_notice_logged:
            self._log("ℹ️ GPU ativada: use um whisper-cli compilado com CUDA.")
            self._gpu_notice_logged = True

        try:
            self.last_error = None
            self.last_segments = None
            self._progress("Transcrevendo...")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

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
                        "elapsed": self._format_elapsed(time.perf_counter() - start_time),
                    }
                )
                arquivo_txt = Path(audio_path).with_suffix(".wav.txt")
                if arquivo_txt.exists():
                    self.last_segments = self._load_segments_for(arquivo_txt)
                    return str(arquivo_txt)

                alternative_txt = Path(audio_path).with_suffix(".txt")
                if alternative_txt.exists():
                    self.last_segments = self._load_segments_for(alternative_txt)
                    return str(alternative_txt)

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

    def _cli_supports_option(self, option):
        help_text = self._get_cli_help()
        # Simple check if option is in help text
        # Improve parsing if needed, but this is usually sufficient and matches original logic
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
            )
            help_text = (result.stdout or "") + (result.stderr or "")
        except Exception:
            help_text = ""
        self._cli_help_cache[self.cli_path] = help_text
        return help_text

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
        srt_path = Path(str(txt_path)[:-4] + ".srt") if str(txt_path).endswith(".txt") else Path(txt_path).with_suffix(".srt")
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
            text = " ".join(lines[timing_idx + 1:]).strip()
            segments.append({
                "start": Transcriber._srt_time_to_seconds(start_str),
                "end": Transcriber._srt_time_to_seconds(end_str),
                "text": text,
            })
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
