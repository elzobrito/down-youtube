import os
from pathlib import Path


def is_portable():
    return os.path.exists("portable.flag")


def ensure_portable_data_dir():
    if not is_portable():
        return None
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
