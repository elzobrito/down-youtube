#!/usr/bin/env python3
"""ASR preprocess WER benchmark (jfk.wav + degraded variants).

Run:
  .venv/bin/python tests/asr_preprocess_benchmark.py

Optional env:
  ASR_BENCH_JFK   path to jfk.wav
  ASR_BENCH_CLI   whisper-cli path
  ASR_BENCH_MODEL ggml model path
  ASR_BENCH_LANG  language (default en)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio import AudioProcessor, ASR_PREPROCESS_PRESETS  # noqa: E402

DEFAULT_JFK = Path.home() / "desenvolvimento" / "whisper.cpp" / "samples" / "jfk.wav"
REF_PATH = Path(__file__).resolve().parent / "fixtures" / "jfk-reference.txt"


def normalize_text(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split() if text else []


def word_error_rate(reference: list[str], hypothesis: list[str]) -> float:
    """Classic Levenshtein WER (substitutions+deletions+insertions)/|ref|."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    n, m = len(reference), len(hypothesis)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if reference[i - 1] == hypothesis[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[n][m] / float(n)


def load_reference() -> str:
    return REF_PATH.read_text(encoding="utf-8").strip()


def ensure_16k_mono(src: Path, dest: Path, ffmpeg: str = "ffmpeg") -> None:
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def mix_noise(src: Path, dest: Path, kind: str, ffmpeg: str = "ffmpeg") -> None:
    """Create degraded variants with FFmpeg filters (no network)."""
    if kind == "clean":
        shutil.copy2(src, dest)
        return
    if kind == "stationary_noise":
        # Aggressive stationary noise so off is non-trivial on jfk
        af = (
            "aformat=sample_fmts=s16:sample_rates=16000:channel_layouts=mono,"
            "volume=0.55,"
            "aeval=val(0)+0.55*random(0):c=same"
        )
    elif kind == "tonal_rhythm":
        # Loud tonal/rhythmic bed under speech
        af = (
            "aformat=sample_fmts=s16:sample_rates=16000:channel_layouts=mono,"
            "volume=0.7,"
            "aeval=val(0)+0.45*sin(2*PI*180*t)+0.35*sin(2*PI*360*t)"
            "+0.2*sin(2*PI*90*t)*((mod(t*4\\,1)>0.5)):c=same"
        )
    else:
        raise ValueError(kind)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-af",
        af,
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: pure Python noise if aeval unavailable
        _python_mix_noise(src, dest, kind)


def _python_mix_noise(src: Path, dest: Path, kind: str) -> None:
    with wave.open(str(src), "rb") as wf:
        rate = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if sw != 2 or nch != 1:
        shutil.copy2(src, dest)
        return
    samples = list(struct.unpack("<" + "h" * (len(frames) // 2), frames))
    out = []
    for i, s in enumerate(samples):
        t = i / float(rate)
        if kind == "stationary_noise":
            noise = int(9000 * ((i * 1103515245 + 12345) % 1000 / 1000.0 - 0.5) * 2)
            s = int(s * 0.55)
        else:
            import math

            noise = int(
                7000 * math.sin(2 * math.pi * 180 * t)
                + 5000 * math.sin(2 * math.pi * 360 * t)
                + 3000 * math.sin(2 * math.pi * 90 * t) * (1 if (int(t * 4) % 2) else 0)
            )
            s = int(s * 0.7)
        val = max(-32767, min(32767, s + noise))
        out.append(val)
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * len(out), *out))


def run_whisper(cli: str, model: str, audio: Path, out_dir: Path, language: str) -> str:
    base = out_dir / audio.stem
    cmd = [
        cli,
        "-m",
        model,
        "-f",
        str(audio),
        "-l",
        language,
        "-nt",
        "-np",
        "-t",
        "4",
        "-bs",
        "1",
        "-bo",
        "1",
        "-of",
        str(base),
        "-otxt",
    ]
    # Prefer CPU for reproducibility if GPU flaky; leave default flags
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    txt = Path(str(base) + ".txt")
    if not txt.exists():
        # some builds write audio.wav.txt
        alt = Path(str(audio) + ".txt")
        if alt.exists():
            return alt.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(
            f"whisper failed rc={proc.returncode}: {proc.stderr[-800:] or proc.stdout[-800:]}"
        )
    return txt.read_text(encoding="utf-8", errors="replace")


def evaluate_gates(results: dict) -> dict:
    """Apply WER gates from PLAN.

    - Clean: max regression vs off of 5 percentage points for light/speech
    - Degraded median of best(light,speech) must beat off
    """
    clean = results["cases"]["clean"]
    off_clean = clean["off"]["wer"]
    clean_ok = True
    clean_notes = []
    for preset in ("light", "speech"):
        wer = clean[preset]["wer"]
        delta_pp = (wer - off_clean) * 100.0
        if delta_pp > 5.0 + 1e-9:
            clean_ok = False
            clean_notes.append(f"{preset} clean WER +{delta_pp:.2f}pp > 5pp vs off")
        else:
            clean_notes.append(f"{preset} clean WER delta {delta_pp:.2f}pp OK")

    degraded_names = [k for k in results["cases"] if k != "clean"]
    off_degraded = [results["cases"][n]["off"]["wer"] for n in degraded_names]
    best_degraded = []
    for n in degraded_names:
        best = min(results["cases"][n]["light"]["wer"], results["cases"][n]["speech"]["wer"])
        best_degraded.append(best)

    def median(xs):
        xs = sorted(xs)
        mid = len(xs) // 2
        if not xs:
            return 0.0
        if len(xs) % 2:
            return xs[mid]
        return 0.5 * (xs[mid - 1] + xs[mid])

    med_off = median(off_degraded)
    med_best = median(best_degraded)
    degraded_ok = med_best < med_off - 1e-12
    return {
        "clean_ok": clean_ok,
        "clean_notes": clean_notes,
        "degraded_ok": degraded_ok,
        "median_off_degraded": med_off,
        "median_best_degraded": med_best,
        "approved": clean_ok and degraded_ok,
    }


def run_benchmark() -> dict:
    jfk = Path(os.environ.get("ASR_BENCH_JFK", DEFAULT_JFK))
    cli = os.environ.get(
        "ASR_BENCH_CLI",
        str(Path.home() / ".local/opt/whisper.cpp/bin/whisper-cli"),
    )
    model = os.environ.get(
        "ASR_BENCH_MODEL",
        str(Path.home() / "desenvolvimento/whisper.cpp/models/ggml-small.bin"),
    )
    language = os.environ.get("ASR_BENCH_LANG", "en")
    ffmpeg = os.environ.get("ASR_BENCH_FFMPEG", "ffmpeg")

    if not jfk.is_file():
        raise FileNotFoundError(f"jfk.wav not found: {jfk}")
    if not Path(cli).is_file():
        raise FileNotFoundError(f"whisper-cli not found: {cli}")
    if not Path(model).is_file():
        raise FileNotFoundError(f"model not found: {model}")

    reference = normalize_text(load_reference())
    cases = ("clean", "stationary_noise", "tonal_rhythm")
    presets = ("off", "light", "speech")

    work = Path(tempfile.mkdtemp(prefix="asr_prep_bench_"))
    try:
        clean = work / "jfk_16k.wav"
        ensure_16k_mono(jfk, clean, ffmpeg=ffmpeg)
        base_duration = AudioProcessor().get_wav_duration(str(clean))

        results = {
            "jfk": str(jfk),
            "cli": cli,
            "model": model,
            "language": language,
            "ffmpeg": ffmpeg,
            "reference_words": len(reference),
            "duration_s": base_duration,
            "cases": {},
            "timings_s": {},
        }

        proc = AudioProcessor(ffmpeg_path=ffmpeg)
        t0_all = time.perf_counter()

        for case in cases:
            case_dir = work / case
            case_dir.mkdir()
            degraded = case_dir / f"{case}.wav"
            mix_noise(clean, degraded, case, ffmpeg=ffmpeg)
            results["cases"][case] = {}
            for preset in presets:
                item_dir = case_dir / preset
                item_dir.mkdir()
                wav = item_dir / "work.wav"
                shutil.copy2(degraded, wav)
                t0 = time.perf_counter()
                prep = proc.preprocess_for_asr(str(wav), preset)
                assert AudioProcessor.validate_asr_wav(str(wav))
                hyp_text = run_whisper(cli, model, wav, item_dir, language)
                elapsed = time.perf_counter() - t0
                hyp = normalize_text(hyp_text)
                wer = word_error_rate(reference, hyp)
                results["cases"][case][preset] = {
                    "wer": wer,
                    "wer_pct": round(wer * 100, 2),
                    "hypothesis": hyp_text.strip()[:500],
                    "applied_preset": prep.applied_preset,
                    "fallback_reason": prep.fallback_reason,
                    "source_hash": prep.source_audio_hash[:16],
                    "audio_hash": prep.audio_hash[:16],
                    "seconds": round(elapsed, 2),
                }
                results["timings_s"][f"{case}:{preset}"] = round(elapsed, 2)
                # no temps
                leftovers = list(item_dir.glob("*.asrprep.tmp*"))
                if leftovers:
                    raise RuntimeError(f"temp leftovers: {leftovers}")

        results["total_seconds"] = round(time.perf_counter() - t0_all, 2)
        results["gates"] = evaluate_gates(results)
        results["presets"] = {k: v for k, v in ASR_PREPROCESS_PRESETS.items()}
        return results
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    try:
        results = run_benchmark()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 2
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if results["gates"]["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
