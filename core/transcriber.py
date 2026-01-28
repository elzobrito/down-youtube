import os
import subprocess
from pathlib import Path


class Transcriber:
    def __init__(
        self,
        cli_path="whisper-cli",
        model_path="ggml-small.bin",
        language="portuguese",
        threads=0,
        beam_size=1,
        best_of=1,
    ):
        self.cli_path = cli_path
        self.model_path = model_path
        self.language = language
        self.threads = threads
        self.beam_size = beam_size
        self.best_of = best_of

    def transcribe(self, audio_path, output_dir=None):
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio not found: {audio_path}")

        output_dir = output_dir or str(Path(audio_path).parent)
        os.makedirs(output_dir, exist_ok=True)

        command = [
            self.cli_path,
            "-f",
            audio_path,
            "-l",
            self.language,
            "-m",
            self.model_path,
            "--output-txt",
        ]

        if self.threads and self.threads > 0:
            command.extend(["-t", str(self.threads)])
        if self.beam_size and self.beam_size > 0:
            command.extend(["-b", str(self.beam_size)])
        if self.best_of and self.best_of > 0:
            command.extend(["-bo", str(self.best_of)])

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=output_dir,
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        output_path = str(Path(audio_path).with_suffix(".wav.txt"))
        return output_path if os.path.exists(output_path) else None
