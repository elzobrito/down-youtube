import shutil
from pathlib import Path

from config import Config


def backup_database(destination_dir):
    config = Config()
    source = Path(config.db_path)
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / source.name
    if source.exists():
        shutil.copy2(source, target)
    return target


def restore_database(backup_path):
    config = Config()
    source = Path(backup_path)
    destination = Path(config.db_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.copy2(source, destination)
    return destination
