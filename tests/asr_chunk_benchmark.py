#!/usr/bin/env python3
"""Compare legacy and shorter Whisper chunk profiles on one known-bad WAV."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from core.audio import AudioProcessor
from core.transcriber import Transcriber


PROFILES = {
    "30m": {"chunk_seconds": 1800, "overlap_seconds": 0, "prefer_silence": False},
    "10m": {"chunk_seconds": 600, "overlap_seconds": 5, "prefer_silence": True},
    "5m": {"chunk_seconds": 300, "overlap_seconds": 5, "prefer_silence": True},
}


def repetition_metrics(text: str) -> dict:
    words = re.findall(r"\w+", text.casefold())
    lines = [line.strip().casefold() for line in text.splitlines() if line.strip()]
    ngrams = [tuple(words[index : index + 8]) for index in range(max(0, len(words) - 7))]
    counts = Counter(ngrams)
    repeated_ngrams = sum(count - 1 for count in counts.values() if count > 1)
    consecutive_lines = sum(
        1 for previous, current in zip(lines, lines[1:]) if previous == current
    )
    tail_words = words[int(len(words) * 0.8) :]
    tail_ngrams = [
        tuple(tail_words[index : index + 8])
        for index in range(max(0, len(tail_words) - 7))
    ]
    tail_counts = Counter(tail_ngrams)
    tail_repeats = sum(count - 1 for count in tail_counts.values() if count > 1)
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(lines),
        "consecutive_duplicate_lines": consecutive_lines,
        "repeated_8grams": repeated_ngrams,
        "repeated_8gram_ratio": (
            repeated_ngrams / len(ngrams) if ngrams else 0.0
        ),
        "tail_repeated_8grams": tail_repeats,
        "tail_repeated_8gram_ratio": (
            tail_repeats / len(tail_ngrams) if tail_ngrams else 0.0
        ),
    }


def run_profile(args, name: str, profile: dict, duration: float) -> dict:
    profile_dir = args.output_dir / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    linked_audio = profile_dir / args.audio.name
    if not linked_audio.exists():
        linked_audio.symlink_to(args.audio.resolve())

    logs = []
    transcriber = Transcriber(
        cli_path=args.cli,
        model_path=args.model,
        language=args.language,
        threads=args.threads,
        beam_size=args.beam_size,
        best_of=args.best_of,
        use_gpu=not args.no_gpu,
        logger=lambda message: logs.append(str(message)),
        long_audio_threshold_seconds=1,
        chunk_seconds=profile["chunk_seconds"],
        chunk_overlap_seconds=profile["overlap_seconds"],
        prefer_silence_chunks=profile["prefer_silence"],
        silence_search_seconds=15,
        max_context=args.max_context,
        suppress_nst=args.suppress_nst,
        vad_enabled=bool(args.vad_model),
        vad_model_path=str(args.vad_model or ""),
    )
    started = time.perf_counter()
    output = transcriber.transcribe(
        str(linked_audio), output_dir=str(profile_dir), duration=duration
    )
    elapsed = time.perf_counter() - started
    if not output:
        return {
            "profile": name,
            "ok": False,
            "elapsed_seconds": elapsed,
            "error": transcriber.last_error,
            "logs": logs,
        }
    text = Path(output).read_text(encoding="utf-8", errors="replace")
    return {
        "profile": name,
        "ok": True,
        "settings": profile,
        "elapsed_seconds": elapsed,
        "realtime_factor": elapsed / duration if duration else None,
        "segments": len(transcriber.last_segments or []),
        "metrics": repetition_metrics(text),
        "output_txt": str(output),
        "logs": logs,
    }


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", default="portuguese")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=list(PROFILES))
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--beam-size", type=int, default=1)
    parser.add_argument("--best-of", type=int, default=1)
    parser.add_argument("--max-context", type=int, default=-1)
    parser.add_argument("--suppress-nst", action="store_true")
    parser.add_argument("--vad-model", type=Path)
    parser.add_argument("--no-gpu", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    args.audio = args.audio.resolve()
    args.output_dir = args.output_dir.resolve()
    if not args.audio.is_file():
        raise FileNotFoundError(args.audio)
    duration = AudioProcessor().get_wav_duration(str(args.audio))
    if not duration:
        raise RuntimeError(f"unable to read WAV duration: {args.audio}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "audio": str(args.audio),
        "duration_seconds": duration,
        "profiles": [],
    }
    for name in args.profiles:
        print(f"[benchmark] {name}", file=sys.stderr, flush=True)
        result = run_profile(args, name, PROFILES[name], duration)
        report["profiles"].append(result)
        (args.output_dir / "benchmark.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if not result["ok"]:
            break
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in report["profiles"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
