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
    "whisper_threads": "0",
    "whisper_beam_size": "1",
    "whisper_best_of": "1",
    "whisper_use_gpu": "0",
    "theme": "clam",
    "notifications_enabled": "1",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "use_streaming_pipeline": "1",  # Ativar pipeline paralelo por padrão
}


def get_config():
    return Config()
