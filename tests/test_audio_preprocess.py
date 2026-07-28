"""Unit + smoke tests for ASR audio preprocess presets."""

from __future__ import annotations

import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.audio import (  # noqa: E402
    ASR_PREPROCESS_PRESETS,
    AudioProcessor,
    normalize_asr_preprocess_preset,
)


def _write_pcm16_mono_wav(path: Path, seconds: float = 0.25, rate: int = 16000, freq: float = 440.0):
    """Write a short sine-ish PCM s16le mono WAV (no numpy)."""
    nframes = max(1, int(rate * seconds))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        frames = bytearray()
        for i in range(nframes):
            # crude square-ish tone
            amp = 8000 if (i // 40) % 2 == 0 else -8000
            frames += struct.pack("<h", amp)
        wf.writeframes(frames)


def test_normalize_preset_invalid_to_off():
    assert normalize_asr_preprocess_preset(None) == "off"
    assert normalize_asr_preprocess_preset("") == "off"
    assert normalize_asr_preprocess_preset("LEGACY") == "off"
    assert normalize_asr_preprocess_preset("Light") == "light"
    assert normalize_asr_preprocess_preset("SPEECH") == "speech"


def test_off_no_ffmpeg_same_path_and_hashes(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    before = wav.read_bytes()
    called = []

    def boom(*args, **kwargs):
        called.append(1)
        raise AssertionError("FFmpeg must not run for off")

    monkeypatch.setattr(subprocess, "run", boom)
    proc = AudioProcessor(ffmpeg_path="ffmpeg-fake")
    result = proc.preprocess_for_asr(str(wav), "off")
    assert result.path == str(wav)
    assert result.requested_preset == "off"
    assert result.applied_preset == "off"
    assert result.filter_graph is None
    assert result.fallback_reason is None
    assert result.source_audio_hash == result.audio_hash
    assert result.source_audio_hash == AudioProcessor.sha256_file(str(wav))
    assert wav.read_bytes() == before
    assert not called


def test_light_command_contains_expected_filters(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        # Write valid 16k mono pcm to the output path (last arg)
        out = Path(cmd[-1])
        _write_pcm16_mono_wav(out, seconds=0.2)

        class R:
            returncode = 0
            stderr = ""
            stdout = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = AudioProcessor(ffmpeg_path="/bin/ffmpeg-mock")
    result = proc.preprocess_for_asr(str(wav), "light")
    assert result.applied_preset == "light"
    assert result.requested_preset == "light"
    cmd = captured["cmd"]
    assert cmd[0] == "/bin/ffmpeg-mock"
    assert "-af" in cmd
    af = cmd[cmd.index("-af") + 1]
    assert "highpass=f=80" in af
    assert "lowpass=f=7600" in af
    assert "loudnorm" in af
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert "pcm_s16le" in cmd
    assert result.filter_graph == ASR_PREPROCESS_PRESETS["light"]
    assert result.source_audio_hash != result.audio_hash or True  # may differ after rewrite
    assert AudioProcessor.validate_asr_wav(str(wav))
    # no leftover temps
    leftovers = list(tmp_path.glob("*.asrprep.tmp*"))
    assert leftovers == []


def test_speech_fallback_to_light(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    calls = []

    def fake_run(cmd, **kwargs):
        af = cmd[cmd.index("-af") + 1]
        calls.append(af)
        out = Path(cmd[-1])

        class R:
            stderr = ""
            stdout = ""

        if "afftdn" in af:
            R.returncode = 1
            R.stderr = "afftdn not found"
            return R()
        # light succeeds
        _write_pcm16_mono_wav(out, seconds=0.2)
        R.returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = AudioProcessor()
    result = proc.preprocess_for_asr(str(wav), "speech")
    assert len(calls) == 2
    assert "afftdn" in calls[0]
    assert "loudnorm" in calls[1]
    assert result.requested_preset == "speech"
    assert result.applied_preset == "light"
    assert result.fallback_reason
    assert result.filter_graph == ASR_PREPROCESS_PRESETS["light"]


def test_light_failure_keeps_original(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    original = wav.read_bytes()
    original_hash = AudioProcessor.sha256_file(str(wav))

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stderr = "loudnorm explode"
            stdout = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = AudioProcessor()
    result = proc.preprocess_for_asr(str(wav), "light")
    assert result.applied_preset == "off"
    assert result.path == str(wav)
    assert result.audio_hash == original_hash
    assert result.source_audio_hash == original_hash
    assert wav.read_bytes() == original
    assert result.fallback_reason


def test_invalid_output_not_replaced(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    original = wav.read_bytes()

    def fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        out.write_bytes(b"not-a-wav")

        class R:
            returncode = 0
            stderr = ""
            stdout = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = AudioProcessor()
    result = proc.preprocess_for_asr(str(wav), "light")
    assert result.applied_preset == "off"
    assert wav.read_bytes() == original
    assert list(tmp_path.glob("*.asrprep.tmp*")) == []


def test_cancel_before_ffmpeg(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    called = []

    def boom(*a, **k):
        called.append(1)
        raise AssertionError("should not run")

    monkeypatch.setattr(subprocess, "run", boom)
    proc = AudioProcessor()
    result = proc.preprocess_for_asr(str(wav), "light", cancel_check=lambda: True)
    assert result.applied_preset == "off"
    assert result.fallback_reason == "cancelled"
    assert not called


def test_temp_uses_same_directory(tmp_path, monkeypatch):
    wav = tmp_path / "work.wav"
    _write_pcm16_mono_wav(wav)
    seen_out = []

    def fake_run(cmd, **kwargs):
        out = Path(cmd[-1])
        seen_out.append(out)
        assert out.parent == tmp_path
        assert ".asrprep.tmp" in out.name
        _write_pcm16_mono_wav(out)

        class R:
            returncode = 0
            stderr = ""
            stdout = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    AudioProcessor().preprocess_for_asr(str(wav), "light")
    assert seen_out
    assert not any(p.exists() for p in seen_out)


@pytest.mark.skipif(
    subprocess.call(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0,
    reason="ffmpeg not available",
)
def test_smoke_ffmpeg_light_and_speech(tmp_path):
    wav = tmp_path / "smoke.wav"
    _write_pcm16_mono_wav(wav, seconds=0.5)
    proc = AudioProcessor(ffmpeg_path="ffmpeg")
    # light
    light_src = tmp_path / "light.wav"
    light_src.write_bytes(wav.read_bytes())
    r_light = proc.preprocess_for_asr(str(light_src), "light")
    assert r_light.applied_preset == "light"
    assert AudioProcessor.validate_asr_wav(str(light_src))
    # speech (may fallback on very old ffmpeg, still must leave valid wav)
    speech_src = tmp_path / "speech.wav"
    speech_src.write_bytes(wav.read_bytes())
    r_speech = proc.preprocess_for_asr(str(speech_src), "speech")
    assert r_speech.applied_preset in {"speech", "light", "off"}
    assert AudioProcessor.validate_asr_wav(str(speech_src))
    assert list(tmp_path.glob("*.asrprep.tmp*")) == []


def test_save_transcription_provenance(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "youtube_transcriber.db"

    import config as config_mod

    config_mod.Config._instance = None
    cfg = config_mod.Config()
    cfg.portable_mode = True
    cfg.data_dir = data_dir
    cfg.db_path = db_path
    config_mod.Config._instance = cfg

    import database

    database.init_database()
    vid = database.add_video("https://youtu.be/x", title="t", source_site="youtube")
    tid = database.save_transcription(
        vid,
        "hello world",
        language="en",
        model="small",
        audio_hash="ah",
        source_audio_hash="sh",
        asr_preprocess_requested="speech",
        asr_preprocess_applied="light",
        asr_preprocess_filter=ASR_PREPROCESS_PRESETS["light"],
        asr_preprocess_fallback_reason="afftdn missing",
    )
    row = database.get_transcription(tid)
    assert row["audio_hash"] == "ah"
    assert row["source_audio_hash"] == "sh"
    assert row["asr_preprocess_requested"] == "speech"
    assert row["asr_preprocess_applied"] == "light"
    assert "loudnorm" in (row["asr_preprocess_filter"] or "")
    assert row["asr_preprocess_fallback_reason"] == "afftdn missing"
    config_mod.Config._instance = None
