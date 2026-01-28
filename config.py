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


def get_config():
    return Config()
