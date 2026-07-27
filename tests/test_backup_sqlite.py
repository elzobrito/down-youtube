"""Backup must use SQLite API + quick_check + hash, not a silent broken copy."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def live_db(tmp_path, monkeypatch):
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

    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO items (name) VALUES ('alpha')")
    conn.commit()
    # Keep a connection open to simulate app using the DB
    open_conn = sqlite3.connect(str(db_path))
    open_conn.execute("INSERT INTO items (name) VALUES ('beta')")
    open_conn.commit()

    yield db_path, open_conn, tmp_path / "backups"

    open_conn.close()
    config_mod.Config._instance = None


def test_backup_api_quick_check_and_hash(live_db):
    from utils.backup import backup_database, quick_check, sha256_file

    db_path, _open_conn, dest = live_db
    dest.mkdir()
    target = backup_database(dest, source_path=db_path, filename="test.bak.db")
    assert target.exists()
    assert quick_check(target) == "ok"

    meta_path = target.with_suffix(target.suffix + ".meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["quick_check"] == "ok"
    assert meta["sha256"] == sha256_file(target)
    assert meta["method"] == "sqlite3.Connection.backup"

    # Restored content includes rows written while "app" had the DB open
    conn = sqlite3.connect(str(target))
    names = [r[0] for r in conn.execute("SELECT name FROM items ORDER BY id")]
    conn.close()
    assert names == ["alpha", "beta"]


def test_restore_replaces_destination(live_db):
    from utils.backup import backup_database, restore_database

    db_path, open_conn, dest = live_db
    dest.mkdir()
    backup = backup_database(dest, source_path=db_path, filename="snap.db")
    open_conn.close()

    # corrupt live by replacing content differently then restore
    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM items")
    conn.execute("INSERT INTO items (name) VALUES ('gone')")
    conn.commit()
    conn.close()

    restore_database(backup, destination_path=db_path)
    conn = sqlite3.connect(str(db_path))
    names = [r[0] for r in conn.execute("SELECT name FROM items ORDER BY id")]
    conn.close()
    assert names == ["alpha", "beta"]
