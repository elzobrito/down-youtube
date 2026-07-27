"""Safe SQLite backup/restore for the app database.

Primary path uses the SQLite Online Backup API (Connection.backup), then
PRAGMA quick_check and a SHA-256 hash of the destination file. A plain
filesystem copy is never used while the app may have the DB open.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import Config


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def quick_check(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        return str(row[0]) if row else "unknown"
    finally:
        conn.close()


def backup_database(destination_dir, *, source_path=None, filename=None):
    """Backup app DB via sqlite3 backup API.

    Returns the Path of the backup file. Raises RuntimeError if quick_check fails.
    Also writes rag_backup_meta.json (or <backup>.meta.json) next to the backup
    when destination is the standard backups folder pattern; always writes
    sibling meta JSON named ``{backup_name}.meta.json``.
    """
    config = Config()
    source = Path(source_path) if source_path else Path(config.db_path)
    if not source.exists():
        raise FileNotFoundError(f"source database not found: {source}")

    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    if filename:
        target = destination_dir / filename
    else:
        target = destination_dir / f"{source.stem}.bak-{_utc_stamp()}{source.suffix}"

    # Online backup API — safe while source may be open by the app.
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()

    check = quick_check(target)
    if check != "ok":
        try:
            target.unlink(missing_ok=True)
        except TypeError:
            if target.exists():
                target.unlink()
        raise RuntimeError(f"backup quick_check failed: {check}")

    digest = sha256_file(target)
    meta = {
        "source_path": str(source.resolve()),
        "backup_path": str(target.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": target.stat().st_size,
        "sha256": digest,
        "quick_check": check,
        "method": "sqlite3.Connection.backup",
    }
    meta_path = target.with_suffix(target.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def restore_database(backup_path, *, destination_path=None):
    """Restore app DB from a backup file using the backup API (source=backup).

    Validates quick_check on the backup first, then copies into the live path
    via Connection.backup into a temp file and atomic replace.
    """
    config = Config()
    source = Path(backup_path)
    destination = Path(destination_path) if destination_path else Path(config.db_path)
    if not source.exists():
        raise FileNotFoundError(f"backup not found: {source}")

    check = quick_check(source)
    if check != "ok":
        raise RuntimeError(f"backup quick_check failed before restore: {check}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + f".restore-tmp-{_utc_stamp()}")

    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()

    check_tmp = quick_check(tmp)
    if check_tmp != "ok":
        try:
            tmp.unlink()
        except OSError:
            pass
        raise RuntimeError(f"restored temp quick_check failed: {check_tmp}")

    tmp.replace(destination)
    return destination
