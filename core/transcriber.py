import os
import re
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
        ]

        # Enable SRT output when supported so we can persist timed segments.
        if self._cli_supports_option("--output-srt"):
            comando.append("--output-srt")
        elif self._cli_supports_option("-osrt"):
            comando.append("-osrt")

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
                    return str(arquivo_txt)

                alternative_txt = Path(audio_path).with_suffix(".txt")
                if alternative_txt.exists():
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
    def find_srt_file(audio_path):
        """Locate the SRT generated by whisper.cpp for a given audio file."""
        audio = Path(audio_path)
        candidates = [
            Path(f"{audio_path}.srt"),
            audio.with_suffix(".wav.srt"),
            audio.with_suffix(".srt"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    @staticmethod
    def parse_srt_file(filepath):
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        segments = Transcriber.parse_srt(content)
        return segments or None

    @staticmethod
    def parse_srt(content):
        if not content:
            return []

        normalized = content.replace("\ufeff", "").replace("\r\n", "\n").strip()
        if not normalized:
            return []

        blocks = re.split(r"\n\s*\n", normalized)
        segments = []

        for block in blocks:
            lines = [line.strip() for line in block.split("\n") if line.strip()]
            if not lines:
                continue

            if lines[0].isdigit():
                lines = lines[1:]
            if not lines or "-->" not in lines[0]:
                continue

            time_line = lines[0]
            start_end = [part.strip() for part in time_line.split("-->", 1)]
            if len(start_end) != 2:
                continue
            if not start_end[0]:
                continue
            end_tokens = start_end[1].split()
            if not end_tokens:
                continue

            start = Transcriber._parse_srt_timestamp(start_end[0])
            end = Transcriber._parse_srt_timestamp(end_tokens[0])
            if start is None or end is None:
                continue

            text = " ".join(lines[1:]).strip()
            if not text:
                continue

            segments.append(
                {
                    "start": start,
                    "end": max(end, start),
                    "text": text,
                }
            )

        return segments

    @staticmethod
    def _parse_srt_timestamp(value):
        ts = (value or "").strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) != 3:
            return None
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
        except ValueError:
            return None
        return (hours * 3600) + (minutes * 60) + seconds
