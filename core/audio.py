import hashlib
import os
import subprocess
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


ASR_PREPROCESS_PRESETS = {
    "off": None,
    "light": "highpass=f=80,lowpass=f=7600,loudnorm=I=-16:TP=-1.5:LRA=11",
    "speech": "highpass=f=100,lowpass=f=7000,afftdn=nr=12:nf=-25,dynaudnorm=f=150:g=15",
}

VALID_ASR_PRESETS = frozenset(ASR_PREPROCESS_PRESETS.keys())


def normalize_asr_preprocess_preset(value: Optional[str]) -> str:
    """Normalize legacy/invalid values to a valid preset (default off)."""
    if value is None:
        return "off"
    key = str(value).strip().lower()
    if key in VALID_ASR_PRESETS:
        return key
    return "off"


@dataclass(frozen=True)
class AudioPreprocessResult:
    path: str
    requested_preset: str
    applied_preset: str
    filter_graph: Optional[str]
    fallback_reason: Optional[str]
    source_audio_hash: str
    audio_hash: str


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

    @staticmethod
    def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
        hasher = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def validate_asr_wav(path: str) -> bool:
        """True when path is PCM s16le mono 16 kHz with at least one frame."""
        try:
            with wave.open(path, "rb") as wav_file:
                if wav_file.getsampwidth() != 2:
                    return False
                if wav_file.getnchannels() != 1:
                    return False
                if wav_file.getframerate() != 16000:
                    return False
                if wav_file.getnframes() <= 0:
                    return False
            return True
        except Exception:
            return False

    def preprocess_for_asr(
        self,
        audio_path: str,
        preset: str = "off",
        *,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> AudioPreprocessResult:
        """
        Apply FFmpeg ASR preprocess presets atomically on the work WAV.

        - off: same path, no FFmpeg, bytes unchanged, hashes equal
        - light/speech: temp in same dir → validate → os.replace
        - speech failure falls back to light; light failure keeps original
        """
        audio_path = str(audio_path)
        requested = normalize_asr_preprocess_preset(preset)
        source_hash = self.sha256_file(audio_path)

        if requested == "off":
            return AudioPreprocessResult(
                path=audio_path,
                requested_preset="off",
                applied_preset="off",
                filter_graph=None,
                fallback_reason=None,
                source_audio_hash=source_hash,
                audio_hash=source_hash,
            )

        chain = ["speech", "light"] if requested == "speech" else ["light"]
        last_reason = None

        for attempt in chain:
            if cancel_check and cancel_check():
                self._log("⚠️ ASR preprocess cancelado; mantendo WAV original")
                return AudioPreprocessResult(
                    path=audio_path,
                    requested_preset=requested,
                    applied_preset="off",
                    filter_graph=None,
                    fallback_reason="cancelled",
                    source_audio_hash=source_hash,
                    audio_hash=source_hash,
                )

            graph = ASR_PREPROCESS_PRESETS[attempt]
            ok, reason = self._run_preprocess_graph(audio_path, graph, cancel_check=cancel_check)
            if ok:
                audio_hash = self.sha256_file(audio_path)
                fallback_reason = None
                if attempt != requested:
                    fallback_reason = last_reason or f"fallback_to_{attempt}"
                self._progress(
                    {
                        "stage": "audio_preprocess",
                        "requested_preset": requested,
                        "applied_preset": attempt,
                        "fallback_reason": fallback_reason,
                    }
                )
                return AudioPreprocessResult(
                    path=audio_path,
                    requested_preset=requested,
                    applied_preset=attempt,
                    filter_graph=graph,
                    fallback_reason=fallback_reason,
                    source_audio_hash=source_hash,
                    audio_hash=audio_hash,
                )
            last_reason = reason or f"{attempt}_failed"
            self._log(f"⚠️ ASR preprocess '{attempt}' falhou: {last_reason}")

        self._progress(
            {
                "stage": "audio_preprocess",
                "requested_preset": requested,
                "applied_preset": "off",
                "fallback_reason": last_reason,
            }
        )
        return AudioPreprocessResult(
            path=audio_path,
            requested_preset=requested,
            applied_preset="off",
            filter_graph=None,
            fallback_reason=last_reason,
            source_audio_hash=source_hash,
            audio_hash=source_hash,
        )

    def _run_preprocess_graph(
        self,
        audio_path: str,
        filter_graph: str,
        *,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> tuple:
        """Run one FFmpeg graph into a temp file; replace only after validation.

        Returns (success: bool, reason: str|None).
        """
        work = Path(audio_path)
        tmp_path = work.with_name(f"{work.stem}.asrprep.tmp{work.suffix or '.wav'}")
        # Always use .wav suffix for temp clarity
        if tmp_path.suffix.lower() != ".wav":
            tmp_path = work.with_name(f"{work.stem}.asrprep.tmp.wav")
        tmp_path = Path(str(tmp_path))

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            audio_path,
            "-af",
            filter_graph,
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(tmp_path),
        ]

        try:
            if cancel_check and cancel_check():
                return False, "cancelled"

            self._progress(
                {
                    "stage": "audio_preprocess",
                    "message": "Pré-processando áudio para ASR...",
                    "filter_graph": filter_graph,
                }
            )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(work.parent),
            )
            if cancel_check and cancel_check():
                return False, "cancelled"

            if result.returncode != 0:
                self.last_error = result.stderr
                return False, (result.stderr or "ffmpeg_nonzero").strip()[:500] or "ffmpeg_nonzero"

            if not tmp_path.exists():
                return False, "output_missing"

            if not self.validate_asr_wav(str(tmp_path)):
                return False, "output_invalid"

            os.replace(str(tmp_path), audio_path)
            return True, None
        except Exception as exc:
            self.last_error = str(exc)
            return False, str(exc)
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

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

    def split_wav_into_chunks(
        self,
        audio_path,
        chunk_seconds,
        output_dir,
        prefix="chunk",
        overlap_seconds=0,
        prefer_silence=False,
        silence_search_seconds=15,
    ):
        """
        Split a WAV into temporary chunk WAV files with optional overlap.

        ``owned_start``/``owned_end`` describe the non-overlapping timeline
        assigned to a chunk. ``start`` may be earlier because of overlap.
        When requested, boundaries move backwards to the quietest short window
        near the nominal cut without making the owned interval longer.

        Returns dicts with path, start, length, index, owned_start, owned_end.
        Uses pure Python wave I/O (no ffmpeg) so unit tests need no FFmpeg.
        """
        audio_path = str(audio_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        chunk_seconds = float(chunk_seconds)
        overlap_seconds = max(0.0, float(overlap_seconds or 0.0))
        silence_search_seconds = max(0.0, float(silence_search_seconds or 0.0))
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive")
        if overlap_seconds >= chunk_seconds:
            raise ValueError("overlap_seconds must be smaller than chunk_seconds")

        chunks = []
        try:
            with wave.open(audio_path, "rb") as source:
                rate = source.getframerate()
                nchannels = source.getnchannels()
                sampwidth = source.getsampwidth()
                total_frames = source.getnframes()
                duration = total_frames / float(rate) if rate else 0.0
                owned_start = 0.0
                index = 0

                while owned_start < duration - 1e-9:
                    nominal_end = min(duration, owned_start + chunk_seconds)
                    owned_end = nominal_end
                    if (
                        prefer_silence
                        and nominal_end < duration
                        and sampwidth == 2
                        and silence_search_seconds > 0
                    ):
                        search_start = max(
                            owned_start + min(1.0, chunk_seconds / 4.0),
                            nominal_end - silence_search_seconds,
                        )
                        quiet = self._quietest_boundary(
                            source,
                            rate=rate,
                            channels=nchannels,
                            start_seconds=search_start,
                            end_seconds=nominal_end,
                        )
                        if quiet is not None and quiet > owned_start:
                            owned_end = quiet

                    physical_start = (
                        owned_start
                        if index == 0
                        else max(0.0, owned_start - overlap_seconds)
                    )
                    start_frame = max(0, int(round(physical_start * rate)))
                    end_frame = min(total_frames, int(round(owned_end * rate)))
                    to_read = max(0, end_frame - start_frame)
                    source.setpos(start_frame)
                    data = source.readframes(to_read)
                    if not data:
                        break

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
                            "start": physical_start,
                            "length": length_sec,
                            "index": index,
                            "owned_start": owned_start,
                            "owned_end": owned_end,
                        }
                    )
                    owned_start = owned_end
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
    def _quietest_boundary(
        source,
        rate,
        channels,
        start_seconds,
        end_seconds,
        window_seconds=0.25,
    ):
        """Return the center of the lowest-energy 16-bit PCM window."""
        if rate <= 0 or channels <= 0 or end_seconds <= start_seconds:
            return None
        start_frame = max(0, int(round(start_seconds * rate)))
        end_frame = min(source.getnframes(), int(round(end_seconds * rate)))
        if end_frame <= start_frame:
            return None

        original_pos = source.tell()
        try:
            source.setpos(start_frame)
            samples = array("h", source.readframes(end_frame - start_frame))
        finally:
            source.setpos(original_pos)
        if not samples:
            return None

        window_samples = max(channels, int(round(rate * channels * window_seconds)))
        step = max(channels, window_samples // 2)
        best_offset = None
        best_energy = None
        limit = max(1, len(samples) - window_samples + 1)
        for offset in range(0, limit, step):
            window = samples[offset : offset + window_samples]
            if not window:
                continue
            energy = sum(abs(value) for value in window) / len(window)
            if (
                best_energy is None
                or energy < best_energy
                or (energy == best_energy and (best_offset is None or offset > best_offset))
            ):
                best_energy = energy
                best_offset = offset
        if best_offset is None:
            return None
        center_frames = (best_offset + window_samples / 2.0) / channels
        return start_seconds + center_frames / rate

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
