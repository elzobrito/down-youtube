from pathlib import Path
import os


class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        self.portable_mode = os.path.exists("portable.flag")
        if self.portable_mode:
            base_dir = Path(".").resolve()
            self.data_dir = base_dir / "data"
        else:
            self.data_dir = Path.home() / ".youtube_transcriber"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "youtube_transcriber.db"

    def ensure_dir(self, path):
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        return target


DEFAULT_SETTINGS = {
    "ffmpeg_path": r"C:\FFMPEG\bin\ffmpeg.exe",
    "whisper_cli": "whisper-cli",
    "whisper_model": "ggml-small.bin",
    "whisper_language": "portuguese",
    "output_dir": str(Path.home() / "Downloads" / "Transcricoes"),
    "keep_audio": "0",
    "keep_video": "0",
    # When "1" and keep_video is on: yt-dlp best possible video+audio (may use MKV/AV1/VP9)
    "video_download_best_quality": "0",
    # When "1": best audio stream + better clients; if keep_audio, preserve HQ m4a/opus + WAV for Whisper
    "audio_download_best_quality": "0",
    "whisper_threads": "0",
    "whisper_beam_size": "1",
    "whisper_best_of": "1",
    "whisper_use_gpu": "0",
    # Long-audio anti-hallucination: short, overlapped, silence-aware chunks.
    "whisper_long_audio_threshold_seconds": "600",  # > 10 minutes
    "whisper_chunk_seconds": "300",  # 5-minute owned intervals
    "whisper_chunk_overlap_seconds": "5",
    "whisper_chunk_silence_search_seconds": "15",
    "whisper_prefer_silence_chunks": "1",
    # whisper.cpp decoder hardening. The worker auto-discovers a nearby Silero model.
    "whisper_vad_enabled": "1",
    "whisper_vad_model": "",
    "whisper_max_context": "0",
    "whisper_suppress_nst": "1",
    "theme": "Light (Custom)",
    "notifications_enabled": "1",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    # Dedicated local model for conservative post-ASR transcript improvement.
    "transcript_improvement_model": "phi4-mini:latest",
    "use_streaming_pipeline": "1",  # Ativar pipeline paralelo por padrão
    # Long-term memory (rag-sqlite projection) — see docs/plans/PLAN-youtube-ltm-rag.md
    "rag_enabled": "1",
    "rag_sqlite_cli": "rag-sqlite",
    "rag_sqlite_root": str(Path.home() / "desenvolvimento" / "rag-sqlite"),
    "rag_db_name": "youtube_rag.sqlite",
    "rag_embedding_provider": "ollama",  # use hash offline/tests; ollama for quality
    "rag_embedding_model": "embeddinggemma",
    "rag_top_k": "8",
    "rag_min_score": "0.15",
    "rag_max_context_chars": "16000",
    "rag_expand_neighbors": "1",
    "rag_default_scope": "video",  # chat default: current video
    "rag_index_on_save": "1",
    "rag_fallback_full_text": "1",
    # ASR audio preprocess presets: off | light | speech (see docs/plans/PLAN-asr-audio-preprocess.md)
    "asr_audio_preprocess": "off",
}


def get_config():
    return Config()
