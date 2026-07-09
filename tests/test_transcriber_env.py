import os
from pathlib import Path

from core.transcriber import Transcriber


def test_transcriber_adds_cli_directory_to_ld_library_path(monkeypatch, tmp_path):
    cli_path = tmp_path / "whisper.cpp" / "bin" / "whisper-cli"
    cli_path.parent.mkdir(parents=True)
    cli_path.write_text("#!/bin/sh\n", encoding="utf-8")

    cuda_home = tmp_path / "cuda"
    cuda_lib = cuda_home / "lib64"
    cuda_lib.mkdir(parents=True)

    monkeypatch.setenv("CUDA_HOME", str(cuda_home))
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing/lib")

    env = Transcriber(cli_path=str(cli_path))._build_subprocess_env()

    paths = env["LD_LIBRARY_PATH"].split(":")
    assert paths[0] == str(cli_path.parent)
    assert str(cuda_lib) in paths
    assert "/existing/lib" in paths


def test_transcriber_leaves_path_lookup_cli_without_ld_library_path(monkeypatch):
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    monkeypatch.setattr(Transcriber, "_cuda_library_paths", staticmethod(lambda env: []))

    env = Transcriber(cli_path="whisper-cli")._build_subprocess_env()

    assert "LD_LIBRARY_PATH" not in env
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_transcriber_adds_existing_cuda_library_paths(monkeypatch, tmp_path):
    cuda_home = tmp_path / "cuda-home"
    cuda_path = tmp_path / "cuda-path"
    cuda_home_lib = cuda_home / "lib64"
    cuda_path_lib = cuda_path / "lib64"
    cuda_home_lib.mkdir(parents=True)
    cuda_path_lib.mkdir(parents=True)

    monkeypatch.setenv("CUDA_HOME", str(cuda_home))
    monkeypatch.setenv("CUDA_PATH", str(cuda_path))

    paths = Transcriber._cuda_library_paths(dict(os.environ))

    assert str(cuda_home_lib) in paths
    assert str(cuda_path_lib) in paths
