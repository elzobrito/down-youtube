"""Tests for long-audio chunking (anti-hallucination) in Whisper transcription."""

import wave
from array import array
from pathlib import Path

import pytest

from core.audio import AudioProcessor
from core.transcriber import Transcriber
from core.transcriber import (
    DEFAULT_CHUNK_OVERLAP_SECONDS,
    DEFAULT_CHUNK_SECONDS,
    DEFAULT_LONG_AUDIO_THRESHOLD_SECONDS,
)
from core.worker import TranscriberWorker


def _write_silent_wav(path, duration_sec, sample_rate=16000):
    path = Path(path)
    nframes = int(sample_rate * duration_sec)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * nframes)
    return path


def test_should_chunk_threshold_boundary():
    assert AudioProcessor.should_chunk_duration(3600, 3600) is False
    assert AudioProcessor.should_chunk_duration(3600.1, 3600) is True
    assert AudioProcessor.should_chunk_duration(7200, 3600) is True
    assert AudioProcessor.should_chunk_duration(None, 3600) is False
    assert AudioProcessor.should_chunk_duration(100, 3600) is False
    assert DEFAULT_LONG_AUDIO_THRESHOLD_SECONDS == 600
    assert DEFAULT_CHUNK_SECONDS == 300
    assert DEFAULT_CHUNK_OVERLAP_SECONDS == 5


def test_compute_chunk_ranges_covers_duration():
    ranges = AudioProcessor.compute_chunk_ranges(3660, 1800)
    assert ranges == [(0.0, 1800.0), (1800.0, 1800.0), (3600.0, 60.0)]

    ranges_exact = AudioProcessor.compute_chunk_ranges(3600, 1800)
    assert ranges_exact == [(0.0, 1800.0), (1800.0, 1800.0)]

    assert AudioProcessor.compute_chunk_ranges(0, 1800) == []
    assert AudioProcessor.compute_chunk_ranges(100, 0) == []


def test_split_wav_into_chunks_and_cleanup(tmp_path):
    wav = _write_silent_wav(tmp_path / "long.wav", duration_sec=5.0)
    processor = AudioProcessor()
    chunks = processor.split_wav_into_chunks(
        str(wav), chunk_seconds=2.0, output_dir=tmp_path / "parts", prefix="p"
    )
    assert len(chunks) == 3
    assert abs(chunks[0]["start"] - 0.0) < 1e-6
    assert abs(chunks[1]["start"] - 2.0) < 1e-6
    assert abs(chunks[2]["length"] - 1.0) < 1e-3
    for item in chunks:
        assert Path(item["path"]).exists()
        assert abs(processor.get_wav_duration(item["path"]) - item["length"]) < 0.05

    # Simulate whisper side-outputs
    side = Path(chunks[0]["path"] + ".txt")
    side.write_text("hello", encoding="utf-8")
    AudioProcessor.cleanup_chunk_artifacts([c["path"] for c in chunks])
    for item in chunks:
        assert not Path(item["path"]).exists()
    assert not side.exists()


def test_split_chunks_include_overlap_and_owned_timeline(tmp_path):
    wav = _write_silent_wav(tmp_path / "overlap.wav", duration_sec=5.0)
    chunks = AudioProcessor().split_wav_into_chunks(
        str(wav),
        chunk_seconds=2.0,
        overlap_seconds=0.5,
        output_dir=tmp_path / "parts",
    )
    assert [(c["owned_start"], c["owned_end"]) for c in chunks] == [
        (0.0, 2.0),
        (2.0, 4.0),
        (4.0, 5.0),
    ]
    assert chunks[0]["start"] == pytest.approx(0.0)
    assert chunks[1]["start"] == pytest.approx(1.5)
    assert chunks[2]["start"] == pytest.approx(3.5)
    assert chunks[1]["length"] == pytest.approx(2.5)


def test_silence_aware_cut_moves_boundary_backwards(tmp_path):
    rate = 16000
    samples = array("h")
    for index in range(rate * 4):
        second = index / rate
        samples.append(0 if 1.45 <= second <= 1.70 else 9000)
    wav = tmp_path / "silence-boundary.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())

    chunks = AudioProcessor().split_wav_into_chunks(
        str(wav),
        chunk_seconds=2.0,
        overlap_seconds=0.25,
        prefer_silence=True,
        silence_search_seconds=1.0,
        output_dir=tmp_path / "parts",
    )
    assert 1.45 <= chunks[0]["owned_end"] <= 1.70
    assert chunks[1]["start"] == pytest.approx(
        chunks[0]["owned_end"] - 0.25, abs=0.02
    )


def test_shift_srt_offsets_timestamps():
    srt = (
        "1\n"
        "00:00:01,000 --> 00:00:02,500\n"
        "hello\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:04,000\n"
        "world\n"
    )
    shifted = Transcriber._shift_srt_content(srt, 1800.0)
    assert "00:30:01,000 --> 00:30:02,500" in shifted
    assert "00:30:03,000 --> 00:30:04,000" in shifted
    segs = Transcriber._parse_srt(shifted)
    assert segs[0]["start"] == pytest.approx(1801.0)
    assert segs[0]["end"] == pytest.approx(1802.5)


def test_renumber_srt_blocks_continues_index():
    srt = "1\n00:00:00,000 --> 00:00:01,000\nA\n\n2\n00:00:01,000 --> 00:00:02,000\nB\n"
    blocks, next_idx = Transcriber._renumber_srt_blocks(srt, start_index=10)
    assert next_idx == 12
    assert blocks[0].startswith("10\n")
    assert blocks[1].startswith("11\n")


def test_transcribe_short_audio_does_not_split(monkeypatch, tmp_path):
    wav = _write_silent_wav(tmp_path / "short.wav", duration_sec=2.0)
    calls = []

    def fake_single(self, audio_path, output_dir=None, duration=None, set_segments=True):
        calls.append({"path": audio_path, "duration": duration})
        out = Path(str(audio_path) + ".txt")
        out.write_text("ok", encoding="utf-8")
        Path(str(audio_path) + ".srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nok\n", encoding="utf-8"
        )
        return str(out)

    monkeypatch.setattr(Transcriber, "_transcribe_single", fake_single)
    split_calls = []

    def boom(*args, **kwargs):
        split_calls.append(True)
        raise AssertionError("split should not run for short audio")

    monkeypatch.setattr(AudioProcessor, "split_wav_into_chunks", boom)

    t = Transcriber(
        long_audio_threshold_seconds=3600,
        chunk_seconds=1800,
        chunk_overlap_seconds=0,
    )
    result = t.transcribe(str(wav), output_dir=str(tmp_path), duration=2.0)
    assert result is not None
    assert len(calls) == 1
    assert split_calls == []


def test_transcribe_long_audio_splits_merges_and_cleans(monkeypatch, tmp_path):
    # 5s audio with threshold 3s and chunk 2s -> 3 chunks
    wav = _write_silent_wav(tmp_path / "long.wav", duration_sec=5.0)
    single_calls = []

    def fake_single(self, audio_path, output_dir=None, duration=None, set_segments=True):
        single_calls.append(Path(audio_path).name)
        # Whisper-style names: file.wav.txt / file.wav.srt
        txt = Path(str(audio_path) + ".txt")
        srt = Path(str(audio_path) + ".srt")
        # Encode chunk index in text for merge verification
        name = Path(audio_path).stem
        idx = name.split("_")[-1] if "_" in name else "0"
        txt.write_text(f"part-{idx}", encoding="utf-8")
        srt.write_text(
            f"1\n00:00:00,100 --> 00:00:00,900\npart-{idx}\n",
            encoding="utf-8",
        )
        return str(txt)

    monkeypatch.setattr(Transcriber, "_transcribe_single", fake_single)

    progress_events = []
    t = Transcriber(
        long_audio_threshold_seconds=3,
        chunk_seconds=2,
        chunk_overlap_seconds=0,
        prefer_silence_chunks=False,
        progress_callback=lambda d: progress_events.append(d),
    )
    result = t.transcribe(str(wav), output_dir=str(tmp_path), duration=5.0)
    assert result is not None
    assert len(single_calls) == 3

    final_txt = Path(result)
    assert final_txt.exists()
    body = final_txt.read_text(encoding="utf-8")
    assert "part-000" in body
    assert "part-001" in body
    assert "part-002" in body

    final_srt = Path(str(wav) + ".srt")
    if not final_srt.exists():
        # may be written next to result
        final_srt = final_txt.with_suffix(".srt") if final_txt.name.endswith(".txt") else Path(str(final_txt)[:-4] + ".srt")
        if str(result).endswith(".txt"):
            final_srt = Path(str(result)[:-4] + ".srt")
    assert final_srt.exists(), f"missing srt near {result}"
    srt_text = final_srt.read_text(encoding="utf-8")
    # second chunk starts at ~2s
    assert "00:00:02," in srt_text or "00:00:02." in srt_text
    # third chunk starts at ~4s
    assert "00:00:04," in srt_text or "00:00:04." in srt_text

    segs = t.last_segments
    assert segs and len(segs) >= 3
    assert segs[0]["start"] == pytest.approx(0.1, abs=0.05)
    assert segs[1]["start"] == pytest.approx(2.1, abs=0.05)
    assert segs[2]["start"] == pytest.approx(4.1, abs=0.05)

    # temp chunk dir/files must be cleaned
    leftovers = list(tmp_path.glob("**/long_part_*.wav"))
    assert leftovers == []
    assert any(isinstance(e, dict) and e.get("percent") == 100 for e in progress_events)


def test_chunk_progress_wrapper_does_not_recurse(monkeypatch, tmp_path):
    """Regression: wrapping progress via self._progress caused RecursionError."""
    wav = _write_silent_wav(tmp_path / "long.wav", duration_sec=5.0)
    progress_events = []

    def outer_progress(data):
        progress_events.append(data)
        # If recursion happens, this blows the stack before we finish.
        assert len(progress_events) < 500

    def fake_single(self, audio_path, output_dir=None, duration=None, set_segments=True):
        # Simulate whisper progress callbacks during a chunk.
        self._progress({"stage": "transcription", "percent": 10, "elapsed": "00:01"})
        self._progress({"stage": "transcription", "percent": 50, "elapsed": "00:02"})
        self._progress("Transcrevendo...")
        out = Path(str(audio_path) + ".txt")
        out.write_text("ok", encoding="utf-8")
        Path(str(audio_path) + ".srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nok\n", encoding="utf-8"
        )
        return str(out)

    monkeypatch.setattr(Transcriber, "_transcribe_single", fake_single)
    t = Transcriber(
        long_audio_threshold_seconds=3,
        chunk_seconds=2,
        chunk_overlap_seconds=0,
        progress_callback=outer_progress,
    )
    result = t.transcribe(str(wav), output_dir=str(tmp_path), duration=5.0)
    assert result is not None
    assert t.last_error is None
    # Outer callback received both dict progress and string messages without recursion
    assert any(isinstance(e, dict) and e.get("percent") is not None for e in progress_events)
    assert any(isinstance(e, str) for e in progress_events)


def test_transcribe_chunked_respects_cancel(monkeypatch, tmp_path):
    wav = _write_silent_wav(tmp_path / "long.wav", duration_sec=5.0)
    cancelled = {"n": 0}

    def cancel():
        cancelled["n"] += 1
        # cancel after first progress / early in chunked
        return cancelled["n"] > 1

    def fake_single(self, audio_path, output_dir=None, duration=None, set_segments=True):
        out = Path(str(audio_path) + ".txt")
        out.write_text("x", encoding="utf-8")
        Path(str(audio_path) + ".srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8"
        )
        return str(out)

    monkeypatch.setattr(Transcriber, "_transcribe_single", fake_single)
    t = Transcriber(
        long_audio_threshold_seconds=3,
        chunk_seconds=2,
        chunk_overlap_seconds=0,
        cancel_check_callback=cancel,
    )
    result = t.transcribe(str(wav), output_dir=str(tmp_path), duration=5.0)
    assert result is None
    assert t.last_error == "Processamento cancelado"
    assert list(tmp_path.glob("**/long_part_*.wav")) == []


def test_timestamp_merge_drops_overlap_duplicate():
    transcriber = Transcriber(chunk_overlap_seconds=5)
    existing = [{"start": 294.0, "end": 300.0, "text": "frase da fronteira"}]
    incoming = [
        {"start": 296.0, "end": 301.0, "text": "frase da fronteira"},
        {"start": 301.0, "end": 304.0, "text": "conteúdo novo"},
    ]
    merged = transcriber._merge_timestamped_segments(
        existing, incoming, owned_start=300.0
    )
    assert [segment["text"] for segment in merged] == [
        "frase da fronteira",
        "conteúdo novo",
    ]


def test_timestamp_merge_caps_exact_consecutive_loop_at_two():
    transcriber = Transcriber(chunk_overlap_seconds=5)
    incoming = [
        {"start": index * 2.0, "end": index * 2.0 + 2.0, "text": "loop exato"}
        for index in range(20)
    ]
    merged = transcriber._merge_timestamped_segments(
        [], incoming, owned_start=0.0
    )
    assert len(merged) == 2
    assert transcriber.last_suppressed_repeat_segments == 18


def test_text_fallback_drops_word_overlap():
    merged = Transcriber._merge_text_overlap(
        "um dois três quatro",
        "três quatro cinco seis",
    )
    assert merged == "um dois três quatro\ncinco seis"


def test_whisper_hardening_options_are_added_when_supported(monkeypatch, tmp_path):
    wav = _write_silent_wav(tmp_path / "short.wav", duration_sec=1.0)
    vad_model = tmp_path / "vad.bin"
    vad_model.write_bytes(b"vad")
    captured = {}

    class FakeProcess:
        def poll(self):
            return 0

        def wait(self):
            return 0

        def terminate(self):
            return None

    def fake_popen(command, **kwargs):
        captured["command"] = command
        Path(str(wav) + ".txt").write_text("ok", encoding="utf-8")
        Path(str(wav) + ".srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nok\n",
            encoding="utf-8",
        )
        return FakeProcess()

    monkeypatch.setattr("core.transcriber.subprocess.Popen", fake_popen)
    monkeypatch.setattr(Transcriber, "_cli_supports_option", lambda self, option: True)
    transcriber = Transcriber(
        max_context=0,
        suppress_nst=True,
        vad_enabled=True,
        vad_model_path=str(vad_model),
    )
    result = transcriber._transcribe_single(str(wav), str(tmp_path), duration=1.0)
    assert result
    command = captured["command"]
    assert ["--max-context", "0"] == command[
        command.index("--max-context") : command.index("--max-context") + 2
    ]
    assert "--suppress-nst" in command
    assert "--vad" in command
    assert ["--vad-model", str(vad_model)] == command[
        command.index("--vad-model") : command.index("--vad-model") + 2
    ]


def test_vad_model_auto_discovery_prefers_production_name(tmp_path):
    whisper_model = tmp_path / "ggml-small.bin"
    whisper_model.write_bytes(b"whisper")
    test_vad = tmp_path / "for-tests-silero-v6.2.0-ggml.bin"
    test_vad.write_bytes(b"test")
    production_vad = tmp_path / "ggml-silero-v6.2.0.bin"
    production_vad.write_bytes(b"production")
    assert TranscriberWorker._resolve_vad_model(
        "", whisper_model=str(whisper_model)
    ) == str(production_vad.resolve())


def test_vad_model_auto_discovery_honors_configured_path(tmp_path):
    configured = tmp_path / "custom-vad.bin"
    configured.write_bytes(b"custom")
    assert TranscriberWorker._resolve_vad_model(
        str(configured), whisper_model=""
    ) == str(configured.resolve())


def test_worker_migrates_legacy_chunk_settings_without_name_error(monkeypatch):
    settings = {
        "whisper_long_audio_threshold_seconds": "3600",
        "whisper_chunk_seconds": "1800",
    }
    writes = {}

    monkeypatch.setattr("core.worker.get_setting", lambda key: settings.get(key))
    monkeypatch.setattr(
        "core.worker.set_setting",
        lambda key, value: writes.__setitem__(key, value),
    )
    worker = TranscriberWorker(lambda message: None, lambda progress: None, lambda: None)

    config = worker._get_current_config()

    assert config["whisper_long_audio_threshold_seconds"] == 600
    assert config["whisper_chunk_seconds"] == 300
    assert writes == {
        "whisper_long_audio_threshold_seconds": "600",
        "whisper_chunk_seconds": "300",
        "whisper_vad_enabled": "1",
        "whisper_max_context": "0",
        "whisper_suppress_nst": "1",
    }
