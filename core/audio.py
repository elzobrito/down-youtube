import os
import subprocess
import wave
from pathlib import Path

class AudioProcessor:
    def __init__(self, ffmpeg_path="ffmpeg", logger=None, progress_callback=None):
        self.ffmpeg_path = ffmpeg_path
        self.logger = logger
        self.progress_callback = progress_callback
        self.last_error = None

    def _log(self, message):
        if self.logger:
            self.logger(message)

    def _progress(self, message):
        if self.progress_callback:
            self.progress_callback(message)

    def extract_audio(self, video_path, output_dir):
        video_path = str(video_path)
        output_path = str(Path(output_dir) / f"{Path(video_path).stem}.wav")

        command = [
            self.ffmpeg_path,
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
            self._progress({"stage": "status", "message": "Extraindo audio..."})
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=output_dir,
            )
            if result.returncode != 0:
                self.last_error = result.stderr
                self._log(f"❌ Erro ao extrair audio: {result.stderr}")
                return None
            return output_path if os.path.exists(output_path) else None
        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Erro ao extrair audio: {exc}")
            return None

    def normalize_audio(self, audio_path, output_dir):
        audio_path = str(audio_path)
        temp_path = str(Path(audio_path).with_suffix(".norm.wav"))

        command = [
            self.ffmpeg_path,
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
            self._progress({"stage": "status", "message": "Normalizando audio..."})
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=output_dir,
            )
            if result.returncode != 0:
                self._log(f"⚠️ Falha ao normalizar audio: {result.stderr}")
                return audio_path
            if os.path.exists(temp_path):
                os.replace(temp_path, audio_path)
            return audio_path
        except Exception as exc:
            self._log(f"⚠️ Falha ao normalizar audio: {exc}")
            return audio_path
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    def convert_to_wav(self, input_path, output_dir, base_name, status_message="Convertendo audio..."):
        output_path = str(Path(output_dir) / f"{base_name}.wav")
        command = [
            self.ffmpeg_path,
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
            self._progress({"stage": "status", "message": status_message})
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=output_dir,
            )
            if result.returncode != 0:
                self._log(f"❌ Erro ao converter audio: {result.stderr}")
                return None
            return output_path if os.path.exists(output_path) else None
        except Exception as exc:
            self._log(f"❌ Erro ao converter audio: {exc}")
            return None

    def get_wav_duration(self, path):
        try:
            with wave.open(path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                if rate:
                    return frames / float(rate)
        except Exception:
            return None
        return None
