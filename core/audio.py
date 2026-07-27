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

    @staticmethod
    def should_chunk_duration(duration, threshold_seconds=3600):
        """True when audio is long enough to require multi-pass transcription."""
        try:
            return duration is not None and float(duration) > float(threshold_seconds)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def compute_chunk_ranges(duration, chunk_seconds=1800):
        """
        Return list of (start_seconds, length_seconds) covering [0, duration).

        Last chunk may be shorter than chunk_seconds. Empty if duration invalid.
        """
        try:
            duration = float(duration)
            chunk_seconds = float(chunk_seconds)
        except (TypeError, ValueError):
            return []
        if duration <= 0 or chunk_seconds <= 0:
            return []

        ranges = []
        start = 0.0
        while start < duration - 1e-9:
            length = min(chunk_seconds, duration - start)
            if length <= 0:
                break
            ranges.append((start, length))
            start += chunk_seconds
        return ranges

    def split_wav_into_chunks(self, audio_path, chunk_seconds, output_dir, prefix="chunk"):
        """
        Split a WAV into temporary chunk WAV files of at most chunk_seconds.

        Returns list of dicts: {path, start, length, index}.
        Uses pure Python wave I/O (no ffmpeg) so unit tests need no FFmpeg.
        """
        audio_path = str(audio_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        chunk_seconds = float(chunk_seconds)
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive")

        chunks = []
        try:
            with wave.open(audio_path, "rb") as source:
                rate = source.getframerate()
                nchannels = source.getnchannels()
                sampwidth = source.getsampwidth()
                total_frames = source.getnframes()
                frames_per_chunk = max(1, int(round(rate * chunk_seconds)))

                index = 0
                frames_read = 0
                while frames_read < total_frames:
                    if self.progress_callback:
                        # optional light status
                        pass
                    to_read = min(frames_per_chunk, total_frames - frames_read)
                    data = source.readframes(to_read)
                    if not data:
                        break

                    start_sec = frames_read / float(rate) if rate else 0.0
                    length_sec = to_read / float(rate) if rate else 0.0
                    chunk_path = output_dir / f"{prefix}_{index:03d}.wav"

                    with wave.open(str(chunk_path), "wb") as dest:
                        dest.setnchannels(nchannels)
                        dest.setsampwidth(sampwidth)
                        dest.setframerate(rate)
                        dest.writeframes(data)

                    chunks.append(
                        {
                            "path": str(chunk_path),
                            "start": start_sec,
                            "length": length_sec,
                            "index": index,
                        }
                    )
                    frames_read += to_read
                    index += 1
        except Exception as exc:
            self.last_error = str(exc)
            self._log(f"❌ Erro ao fatiar audio: {exc}")
            for item in chunks:
                try:
                    os.remove(item["path"])
                except Exception:
                    pass
            raise

        return chunks

    @staticmethod
    def cleanup_chunk_artifacts(chunk_paths):
        """Remove chunk WAVs and typical whisper outputs next to them."""
        for path in chunk_paths or []:
            base = Path(path)
            candidates = [
                base,
                base.with_suffix(".wav.txt") if base.suffix == ".wav" else base.with_suffix(".txt"),
                Path(str(base) + ".txt"),
                Path(str(base) + ".srt"),
                base.with_suffix(".txt"),
                base.with_suffix(".srt"),
                Path(str(base) + ".wav.txt"),
                Path(str(base) + ".wav.srt"),
            ]
            # Also common whisper naming: file.wav.txt when input is file.wav
            if base.suffix == ".wav":
                candidates.append(Path(str(base) + ".txt"))
                candidates.append(Path(str(base) + ".srt"))
            seen = set()
            for candidate in candidates:
                key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    if candidate.exists() and candidate.is_file():
                        candidate.unlink()
                except Exception:
                    pass
