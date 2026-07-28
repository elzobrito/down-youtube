import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import Config, DEFAULT_SETTINGS


def adapt_datetime(value):
    return value.isoformat()


def convert_datetime(value):
    return datetime.fromisoformat(value.decode())


sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("TIMESTAMP", convert_datetime)




def _base_storage_dir():
    config = Config()
    if config.portable_mode:
        return config.data_dir.parent
    return None


def to_storage_path(path):
    if not path:
        return None
    base_dir = _base_storage_dir()
    if base_dir:
        try:
            return str(Path(path).resolve().relative_to(base_dir))
        except Exception:
            return str(Path(path))
    return str(Path(path))


def from_storage_path(path):
    if not path:
        return None
    base_dir = _base_storage_dir()
    if base_dir:
        return str((base_dir / path).resolve())
    return str(Path(path))


def _column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())


def _ensure_column(cursor, table, column, definition):
    if not _column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _connect():
    return sqlite3.connect(
        str(Config().db_path),
        detect_types=sqlite3.PARSE_DECLTYPES,
    )


def init_database():
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            video_id TEXT,
            title TEXT,
            channel TEXT,
            duration INTEGER,
            thumbnail_url TEXT,
            audio_path TEXT,
            video_path TEXT,
            source_site TEXT DEFAULT 'youtube',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            language TEXT DEFAULT 'pt',
            full_text TEXT,
            segments_json TEXT,
            word_count INTEGER,
            duration_seconds REAL,
            model_used TEXT,
            audio_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
        )
        """
    )

    _ensure_column(cursor, "transcriptions", "audio_hash", "TEXT")
    _ensure_column(cursor, "transcriptions", "is_used", "INTEGER DEFAULT 0")
    _ensure_column(cursor, "transcriptions", "source_audio_hash", "TEXT")
    _ensure_column(cursor, "transcriptions", "asr_preprocess_requested", "TEXT")
    _ensure_column(cursor, "transcriptions", "asr_preprocess_applied", "TEXT")
    _ensure_column(cursor, "transcriptions", "asr_preprocess_filter", "TEXT")
    _ensure_column(cursor, "transcriptions", "asr_preprocess_fallback_reason", "TEXT")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transcription_revisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription_id INTEGER NOT NULL,
            revision_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft', 'approved', 'rejected')),
            is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0, 1)),
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            glossary_version TEXT NOT NULL,
            source_text_sha256 TEXT NOT NULL,
            source_segments_sha256 TEXT,
            improved_text TEXT NOT NULL,
            improved_segments_json TEXT,
            study_markdown TEXT,
            proposals_json TEXT,
            decisions_json TEXT,
            outtakes_json TEXT,
            word_count INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            usage_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            approved_at TIMESTAMP,
            UNIQUE(transcription_id, revision_number),
            FOREIGN KEY (transcription_id)
                REFERENCES transcriptions(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transcription_revision_active
        ON transcription_revisions(transcription_id)
        WHERE is_active = 1
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_transcription_revision_status
        ON transcription_revisions(transcription_id, status, revision_number DESC)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS translations (

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription_id INTEGER NOT NULL,
            target_language TEXT NOT NULL,
            translated_text TEXT,
            segments_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transcription_id) REFERENCES transcriptions(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            status TEXT,
            error_message TEXT,
            output_file TEXT,
            audio_path TEXT,
            video_path TEXT,
            processing_time_seconds REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription_id INTEGER NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transcription_id) REFERENCES transcriptions(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
        """
    )

    _ensure_column(cursor, "videos", "audio_path", "TEXT")
    _ensure_column(cursor, "videos", "video_path", "TEXT")
    _ensure_column(cursor, "history", "audio_path", "TEXT")
    _ensure_column(cursor, "history", "video_path", "TEXT")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'queued',
            input_type TEXT NOT NULL,
            input_value TEXT NOT NULL,
            expanded_count INTEGER DEFAULT 0,
            progress_json TEXT,
            log_tail TEXT,
            error_message TEXT,
            result_transcription_id INTEGER,
            result_video_id INTEGER,
            result_json TEXT,
            worker_id TEXT,
            heartbeat_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        )
        """
    )
    _ensure_column(cursor, "jobs", "result_json", "TEXT")
    _ensure_column(cursor, "jobs", "worker_id", "TEXT")
    _ensure_column(cursor, "jobs", "heartbeat_at", "TIMESTAMP")
    _ensure_column(cursor, "jobs", "options_json", "TEXT")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)"
    )

    # Transactional RAG index queue (replaces rewrite-all JSONL processing)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_index_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transcription_id INTEGER NOT NULL,
            op TEXT NOT NULL DEFAULT 'index',
            status TEXT NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            last_result TEXT,
            claimed_at TIMESTAMP,
            next_attempt_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _ensure_column(cursor, "rag_index_jobs", "next_attempt_at", "TIMESTAMP")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_rag_jobs_status ON rag_index_jobs(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_rag_jobs_tid ON rag_index_jobs(transcription_id)"
    )

    _ensure_column(cursor, "videos", "source_site", "TEXT DEFAULT 'youtube'")
    # Canonicalize every legacy value before the compound identity is used.
    cursor.execute("SELECT id, url, source_site FROM videos")
    for row_id, row_url, current_site in cursor.fetchall():
        canonical_site = normalize_source_site(
            source_site=current_site,
            url=row_url,
        )
        if canonical_site != (current_site or ""):
            cursor.execute(
                "UPDATE videos SET source_site = ? WHERE id = ?",
                (canonical_site, row_id),
            )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_videos_site_vid "
        "ON videos(source_site, video_id)"
    )

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_title ON videos(title)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_transcriptions_video ON transcriptions(video_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_transcriptions_fulltext ON transcriptions(full_text)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON history(status)")

    for key, value in DEFAULT_SETTINGS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )

    conn.commit()
    conn.close()


def normalize_source_site(source_site=None, url=None, info=None):
    """Deterministic platform identity key.

    YouTube extractor variants and hosts collapse to 'youtube'.
    """
    raw = None
    if info and isinstance(info, dict):
        raw = info.get("extractor_key") or info.get("extractor")
    if not raw and source_site:
        raw = source_site
    if raw:
        key = str(raw).strip().lower()
        # yt-dlp keys: Youtube, youtube:tab, YoutubeYtBe, etc.
        if key.startswith("youtube") or key in {"youtu.be", "youtube.com", "www.youtube.com"}:
            return "youtube"
        if key in {"vimeo", "vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
            return "vimeo"
        if key in {"soundcloud", "soundcloud.com", "www.soundcloud.com"}:
            return "soundcloud"
        if key and key not in {"unknown", "none", "null"}:
            # drop nested extractor suffixes like "vimeo:user"
            return key.split(":")[0]
    if url:
        try:
            from urllib.parse import urlparse
            from core.url_resolver import is_youtube_url

            if is_youtube_url(url):
                return "youtube"
            host = (urlparse(url).netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            host = host.split(":")[0]
            if host in {"youtu.be", "youtube.com", "m.youtube.com", "music.youtube.com"}:
                return "youtube"
            if host == "vimeo.com" or host.endswith(".vimeo.com"):
                return "vimeo"
            if host == "soundcloud.com" or host.endswith(".soundcloud.com"):
                return "soundcloud"
            if host:
                return host
        except Exception:
            pass
    return "unknown"


def get_setting(key):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def set_setting(key, value):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def add_video(
    url,
    video_id=None,
    title=None,
    channel=None,
    duration=None,
    thumbnail_url=None,
    audio_path=None,
    video_path=None,
    source_site=None,
):
    conn = _connect()
    cursor = conn.cursor()

    site = normalize_source_site(source_site=source_site, url=url)

    # Identity: (source_site, video_id) when video_id present; else exact URL.
    # Never merge cross-site records that share only video_id.
    row = None
    if video_id:
        cursor.execute(
            """
            SELECT id FROM videos
            WHERE source_site = ? AND video_id = ?
            LIMIT 1
            """,
            (site, video_id),
        )
        row = cursor.fetchone()
    if not row and url:
        cursor.execute(
            """
            SELECT id FROM videos
            WHERE url = ? AND COALESCE(source_site, 'youtube') = ?
            LIMIT 1
            """,
            (url, site),
        )
        row = cursor.fetchone()
    if not row and url and not video_id:
        cursor.execute("SELECT id FROM videos WHERE url = ? LIMIT 1", (url,))
        row = cursor.fetchone()

    if row:
        video_db_id = row[0]
        site_update = None if site == "unknown" else site
        cursor.execute(
            """
            UPDATE videos
            SET title = COALESCE(?, title),
                channel = COALESCE(?, channel),
                duration = COALESCE(?, duration),
                thumbnail_url = COALESCE(?, thumbnail_url),
                audio_path = COALESCE(?, audio_path),
                video_path = COALESCE(?, video_path),
                source_site = COALESCE(?, source_site),
                video_id = COALESCE(?, video_id)
            WHERE id = ?
            """,
            (
                title,
                channel,
                duration,
                thumbnail_url,
                to_storage_path(audio_path),
                to_storage_path(video_path),
                site_update,
                video_id,
                video_db_id,
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO videos
            (url, video_id, title, channel, duration, thumbnail_url, audio_path, video_path, source_site)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                video_id,
                title,
                channel,
                duration,
                thumbnail_url,
                to_storage_path(audio_path),
                to_storage_path(video_path),
                site,
            ),
        )
        video_db_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return video_db_id


def update_video_media(video_id, audio_path=None, video_path=None):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE videos
        SET audio_path = ?, video_path = ?
        WHERE id = ?
        """,
        (to_storage_path(audio_path), to_storage_path(video_path), video_id),
    )
    conn.commit()
    conn.close()


def save_transcription(
    video_id,
    text,
    segments=None,
    language="pt",
    model="small",
    audio_hash=None,
    source_audio_hash=None,
    asr_preprocess_requested=None,
    asr_preprocess_applied=None,
    asr_preprocess_filter=None,
    asr_preprocess_fallback_reason=None,
):
    conn = _connect()
    cursor = conn.cursor()

    word_count = len(text.split()) if text else 0
    duration = 0
    if segments:
        duration = max(seg.get("end", 0) for seg in segments)
    segments_json = json.dumps(segments, ensure_ascii=False) if segments else None

    cursor.execute(
        """
        INSERT INTO transcriptions
        (video_id, language, full_text, segments_json, word_count, duration_seconds,
         model_used, audio_hash, source_audio_hash,
         asr_preprocess_requested, asr_preprocess_applied,
         asr_preprocess_filter, asr_preprocess_fallback_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video_id,
            language,
            text,
            segments_json,
            word_count,
            duration,
            model,
            audio_hash,
            source_audio_hash,
            asr_preprocess_requested,
            asr_preprocess_applied,
            asr_preprocess_filter,
            asr_preprocess_fallback_reason,
        ),
    )

    transcription_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Best-effort LTM enqueue (never fail the writer pipeline)
    try:
        from core.rag_bridge import on_transcription_saved

        on_transcription_saved(transcription_id)
    except Exception:
        pass

    return transcription_id


def _revision_text_sha256(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _revision_segments_sha256(segments):
    if segments is None:
        return None
    payload = json.dumps(
        segments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_or_none(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode_json_or(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _revision_row_to_dict(row):
    if row is None:
        return None
    keys = set(row.keys())

    def field(name, default=None):
        return row[name] if name in keys else default

    return {
        "id": field("id"),
        "transcription_id": field("transcription_id"),
        "revision_number": field("revision_number"),
        "status": field("status"),
        "is_active": int(field("is_active") or 0),
        "model": field("model"),
        "prompt_version": field("prompt_version"),
        "glossary_version": field("glossary_version"),
        "source_text_sha256": field("source_text_sha256"),
        "source_segments_sha256": field("source_segments_sha256"),
        "improved_text": field("improved_text") or "",
        "improved_segments": _decode_json_or(field("improved_segments_json"), None),
        "study_markdown": field("study_markdown") or "",
        "proposals": _decode_json_or(field("proposals_json"), {}),
        "decisions": _decode_json_or(field("decisions_json"), {}),
        "outtakes": _decode_json_or(field("outtakes_json"), []),
        "word_count": int(field("word_count") or 0),
        "chunk_count": int(field("chunk_count") or 0),
        "usage": _decode_json_or(field("usage_json"), {}),
        "created_at": field("created_at"),
        "updated_at": field("updated_at"),
        "approved_at": field("approved_at"),
    }


def create_transcription_revision(
    transcription_id,
    *,
    model,
    prompt_version,
    glossary_version,
    improved_text,
    improved_segments=None,
    study_markdown="",
    proposals=None,
    decisions=None,
    outtakes=None,
    chunk_count=0,
    usage=None,
):
    """Persist a complete draft without modifying the source transcription."""

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        source = cursor.execute(
            "SELECT full_text, segments_json FROM transcriptions WHERE id = ?",
            (transcription_id,),
        ).fetchone()
        if source is None:
            raise ValueError(f"Transcrição inexistente: {transcription_id}")

        source_segments = _decode_json_or(source["segments_json"], None)
        revision_number = cursor.execute(
            """
            SELECT COALESCE(MAX(revision_number), 0) + 1
            FROM transcription_revisions
            WHERE transcription_id = ?
            """,
            (transcription_id,),
        ).fetchone()[0]
        cursor.execute(
            """
            INSERT INTO transcription_revisions (
                transcription_id, revision_number, status, is_active,
                model, prompt_version, glossary_version,
                source_text_sha256, source_segments_sha256,
                improved_text, improved_segments_json, study_markdown,
                proposals_json, decisions_json, outtakes_json,
                word_count, chunk_count, usage_json
            )
            VALUES (?, ?, 'draft', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transcription_id,
                revision_number,
                model,
                prompt_version,
                glossary_version,
                _revision_text_sha256(source["full_text"]),
                _revision_segments_sha256(source_segments),
                improved_text or "",
                _json_or_none(improved_segments),
                study_markdown or "",
                _json_or_none(proposals or {}),
                _json_or_none(decisions or {}),
                _json_or_none(outtakes or []),
                len((improved_text or "").split()),
                int(chunk_count or 0),
                _json_or_none(usage or {}),
            ),
        )
        revision_id = cursor.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_transcription_revision(revision_id)


def get_transcription_revision(revision_id):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM transcription_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        return _revision_row_to_dict(row)
    finally:
        conn.close()


def get_active_transcription_revision(transcription_id):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT * FROM transcription_revisions
            WHERE transcription_id = ? AND is_active = 1 AND status = 'approved'
            ORDER BY revision_number DESC
            LIMIT 1
            """,
            (transcription_id,),
        ).fetchone()
        return _revision_row_to_dict(row)
    finally:
        conn.close()


def list_transcription_revisions(transcription_id, include_rejected=True):
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if include_rejected:
            rows = conn.execute(
                """
                SELECT * FROM transcription_revisions
                WHERE transcription_id = ?
                ORDER BY revision_number DESC
                """,
                (transcription_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM transcription_revisions
                WHERE transcription_id = ? AND status != 'rejected'
                ORDER BY revision_number DESC
                """,
                (transcription_id,),
            ).fetchall()
        return [_revision_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def approve_transcription_revision(
    revision_id,
    *,
    improved_text=None,
    improved_segments=None,
    study_markdown=None,
    decisions=None,
    outtakes=None,
):
    """Atomically activate one draft, rejecting stale source snapshots."""

    conn = _connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        revision = cursor.execute(
            "SELECT * FROM transcription_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if revision is None:
            raise ValueError(f"Revisão inexistente: {revision_id}")
        if revision["status"] != "draft":
            raise ValueError("Somente uma revisão draft pode ser aprovada")

        source = cursor.execute(
            "SELECT full_text, segments_json FROM transcriptions WHERE id = ?",
            (revision["transcription_id"],),
        ).fetchone()
        if source is None:
            raise ValueError("A transcrição de origem não existe mais")
        source_segments = _decode_json_or(source["segments_json"], None)
        if _revision_text_sha256(source["full_text"]) != revision["source_text_sha256"]:
            raise ValueError("A transcrição original mudou desde a geração do draft")
        if _revision_segments_sha256(source_segments) != revision["source_segments_sha256"]:
            raise ValueError("Os segmentos originais mudaram desde a geração do draft")

        final_text = (
            revision["improved_text"] if improved_text is None else improved_text
        ) or ""
        final_segments = (
            revision["improved_segments_json"]
            if improved_segments is None
            else _json_or_none(improved_segments)
        )
        final_markdown = (
            revision["study_markdown"] if study_markdown is None else study_markdown
        ) or ""
        final_decisions = (
            revision["decisions_json"]
            if decisions is None
            else _json_or_none(decisions)
        )
        final_outtakes = (
            revision["outtakes_json"]
            if outtakes is None
            else _json_or_none(outtakes)
        )

        cursor.execute(
            """
            UPDATE transcription_revisions
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE transcription_id = ? AND is_active = 1
            """,
            (revision["transcription_id"],),
        )
        cursor.execute(
            """
            UPDATE transcription_revisions
            SET status = 'approved', is_active = 1,
                improved_text = ?, improved_segments_json = ?,
                study_markdown = ?, decisions_json = ?, outtakes_json = ?,
                word_count = ?, updated_at = CURRENT_TIMESTAMP,
                approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                final_text,
                final_segments,
                final_markdown,
                final_decisions,
                final_outtakes,
                len(final_text.split()),
                revision_id,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    approved = get_transcription_revision(revision_id)
    try:
        from core.rag_bridge import on_transcription_saved

        on_transcription_saved(approved["transcription_id"])
    except Exception:
        pass
    return approved


def reject_transcription_revision(revision_id):
    conn = _connect()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN IMMEDIATE")
        row = cursor.execute(
            "SELECT status, is_active FROM transcription_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Revisão inexistente: {revision_id}")
        if row[0] != "draft" or row[1]:
            raise ValueError("Somente um draft inativo pode ser rejeitado")
        cursor.execute(
            """
            UPDATE transcription_revisions
            SET status = 'rejected', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (revision_id,),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    rejected = get_transcription_revision(revision_id)
    try:
        from core.rag_bridge import on_transcription_saved

        on_transcription_saved(rejected["transcription_id"])
    except Exception:
        pass
    return rejected


def deactivate_transcription_revision(transcription_id):
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE transcription_revisions
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE transcription_id = ? AND is_active = 1
            """,
            (transcription_id,),
        )
        conn.commit()
    finally:
        conn.close()
    try:
        from core.rag_bridge import on_transcription_saved

        on_transcription_saved(transcription_id)
    except Exception:
        pass


def get_transcription(transcription_id):
    """Load one transcription with video metadata via named columns.

    Uses an explicit SELECT (not t.*) so column order never shifts when
    new transcriptions columns such as is_used are added.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            t.id AS id,
            t.video_id AS video_id,
            t.language AS language,
            t.full_text AS full_text,
            t.segments_json AS segments_json,
            t.word_count AS word_count,
            t.duration_seconds AS duration_seconds,
            t.model_used AS model_used,
            t.audio_hash AS audio_hash,
            t.source_audio_hash AS source_audio_hash,
            t.asr_preprocess_requested AS asr_preprocess_requested,
            t.asr_preprocess_applied AS asr_preprocess_applied,
            t.asr_preprocess_filter AS asr_preprocess_filter,
            t.asr_preprocess_fallback_reason AS asr_preprocess_fallback_reason,
            t.created_at AS created_at,
            t.updated_at AS updated_at,
            COALESCE(t.is_used, 0) AS is_used,
            ar.id AS active_revision_id,
            ar.revision_number AS active_revision_number,
            ar.status AS active_revision_status,
            ar.model AS active_revision_model,
            ar.prompt_version AS active_revision_prompt_version,
            ar.glossary_version AS active_revision_glossary_version,
            ar.source_text_sha256 AS active_revision_source_text_sha256,
            ar.source_segments_sha256 AS active_revision_source_segments_sha256,
            ar.improved_text AS active_revision_text,
            ar.improved_segments_json AS active_revision_segments_json,
            ar.study_markdown AS active_revision_study_markdown,
            ar.proposals_json AS active_revision_proposals_json,
            ar.decisions_json AS active_revision_decisions_json,
            ar.outtakes_json AS active_revision_outtakes_json,
            ar.word_count AS active_revision_word_count,
            ar.chunk_count AS active_revision_chunk_count,
            ar.usage_json AS active_revision_usage_json,
            ar.created_at AS active_revision_created_at,
            ar.updated_at AS active_revision_updated_at,
            ar.approved_at AS active_revision_approved_at,
            v.title AS video_title,
            v.url AS video_url,
            v.channel AS channel,
            v.video_id AS youtube_video_id,
            v.audio_path AS audio_path,
            v.video_path AS video_path
        FROM transcriptions t
        JOIN videos v ON t.video_id = v.id
        LEFT JOIN transcription_revisions ar
          ON ar.transcription_id = t.id
         AND ar.is_active = 1
         AND ar.status = 'approved'
        WHERE t.id = ?
        """,
        (transcription_id,),
    )

    result = cursor.fetchone()
    conn.close()

    if result:
        segments_raw = result["segments_json"]
        original_segments = json.loads(segments_raw) if segments_raw else None
        active_revision = None
        if result["active_revision_id"] is not None:
            active_revision = {
                "id": result["active_revision_id"],
                "transcription_id": result["id"],
                "revision_number": result["active_revision_number"],
                "status": result["active_revision_status"],
                "is_active": 1,
                "model": result["active_revision_model"],
                "prompt_version": result["active_revision_prompt_version"],
                "glossary_version": result["active_revision_glossary_version"],
                "source_text_sha256": result["active_revision_source_text_sha256"],
                "source_segments_sha256": result[
                    "active_revision_source_segments_sha256"
                ],
                "improved_text": result["active_revision_text"] or "",
                "improved_segments": _decode_json_or(
                    result["active_revision_segments_json"], None
                ),
                "study_markdown": result["active_revision_study_markdown"] or "",
                "proposals": _decode_json_or(
                    result["active_revision_proposals_json"], {}
                ),
                "decisions": _decode_json_or(
                    result["active_revision_decisions_json"], {}
                ),
                "outtakes": _decode_json_or(
                    result["active_revision_outtakes_json"], []
                ),
                "word_count": int(result["active_revision_word_count"] or 0),
                "chunk_count": int(result["active_revision_chunk_count"] or 0),
                "usage": _decode_json_or(
                    result["active_revision_usage_json"], {}
                ),
                "created_at": result["active_revision_created_at"],
                "updated_at": result["active_revision_updated_at"],
                "approved_at": result["active_revision_approved_at"],
            }
        effective_text = (
            active_revision["improved_text"]
            if active_revision is not None
            else result["full_text"]
        )
        effective_segments = (
            active_revision["improved_segments"]
            if active_revision is not None
            else original_segments
        )
        return {
            "id": result["id"],
            "video_id": result["video_id"],
            "language": result["language"],
            "full_text": result["full_text"],
            "segments": original_segments,
            "active_revision": active_revision,
            "effective_text": effective_text,
            "effective_segments": effective_segments,
            "effective_word_count": len((effective_text or "").split()),
            "study_markdown": (
                active_revision["study_markdown"] if active_revision else ""
            ),
            "word_count": result["word_count"],
            "duration": result["duration_seconds"],
            "model": result["model_used"],
            "audio_hash": result["audio_hash"],
            "source_audio_hash": result["source_audio_hash"],
            "asr_preprocess_requested": result["asr_preprocess_requested"],
            "asr_preprocess_applied": result["asr_preprocess_applied"],
            "asr_preprocess_filter": result["asr_preprocess_filter"],
            "asr_preprocess_fallback_reason": result["asr_preprocess_fallback_reason"],
            "created_at": result["created_at"],
            "updated_at": result["updated_at"],
            "is_used": result["is_used"],
            "video_title": result["video_title"],
            "video_url": result["video_url"],
            "channel": result["channel"],
            "youtube_video_id": result["youtube_video_id"],
            "audio_path": from_storage_path(result["audio_path"]) if result["audio_path"] else None,
            "video_path": from_storage_path(result["video_path"]) if result["video_path"] else None,
        }
    return None


def get_transcription_by_video(video_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM transcriptions
        WHERE video_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (video_id,),
    )
    result = cursor.fetchone()
    conn.close()
    return result


def get_latest_transcription_for_source(video_id=None, url=None, source_site=None):
    conn = _connect()
    cursor = conn.cursor()

    site = normalize_source_site(source_site=source_site, url=url) if (source_site or url) else None

    if video_id and site:
        cursor.execute(
            """
            SELECT t.id, t.created_at
            FROM transcriptions t
            JOIN videos v ON t.video_id = v.id
            WHERE v.video_id = ? AND COALESCE(v.source_site, 'youtube') = ?
            ORDER BY t.created_at DESC
            LIMIT 1
            """,
            (video_id, site),
        )
    elif video_id:
        # Legacy callers without site: prefer youtube, then any
        cursor.execute(
            """
            SELECT t.id, t.created_at
            FROM transcriptions t
            JOIN videos v ON t.video_id = v.id
            WHERE v.video_id = ?
            ORDER BY
                CASE WHEN COALESCE(v.source_site, 'youtube') = 'youtube' THEN 0 ELSE 1 END,
                t.created_at DESC
            LIMIT 1
            """,
            (video_id,),
        )
    elif url:
        if site:
            cursor.execute(
                """
                SELECT t.id, t.created_at
                FROM transcriptions t
                JOIN videos v ON t.video_id = v.id
                WHERE v.url = ? AND COALESCE(v.source_site, 'youtube') = ?
                ORDER BY t.created_at DESC
                LIMIT 1
                """,
                (url, site),
            )
        else:
            cursor.execute(
                """
                SELECT t.id, t.created_at
                FROM transcriptions t
                JOIN videos v ON t.video_id = v.id
                WHERE v.url = ?
                ORDER BY t.created_at DESC
                LIMIT 1
                """,
                (url,),
            )
    else:
        conn.close()
        return None

    result = cursor.fetchone()
    conn.close()
    return result


def get_transcription_by_audio_hash(audio_hash):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, created_at
        FROM transcriptions
        WHERE audio_hash = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (audio_hash,),
    )
    result = cursor.fetchone()
    conn.close()
    return result


def search_transcriptions(query, limit=50):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.id, t.video_id, v.title, v.channel,
               COALESCE(ar.word_count, t.word_count), t.language, t.created_at,
               substr(
                   COALESCE(ar.improved_text, t.full_text),
                   max(
                       1,
                       instr(
                           lower(COALESCE(ar.improved_text, t.full_text)),
                           lower(?)
                       ) - 50
                   ),
                   150
               )
               AS snippet
        FROM transcriptions t
        JOIN videos v ON t.video_id = v.id
        LEFT JOIN transcription_revisions ar
          ON ar.transcription_id = t.id
         AND ar.is_active = 1
         AND ar.status = 'approved'
        WHERE COALESCE(ar.improved_text, t.full_text) LIKE ?
        ORDER BY t.created_at DESC
        LIMIT ?
        """,
        (query, f"%{query}%", limit),
    )
    results = cursor.fetchall()
    conn.close()
    return results


def get_all_transcriptions(limit=100, offset=0):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT t.id, v.title, v.channel, t.language,
               COALESCE(ar.word_count, t.word_count),
               t.duration_seconds, t.created_at, COALESCE(t.is_used, 0)
        FROM transcriptions t
        JOIN videos v ON t.video_id = v.id
        LEFT JOIN transcription_revisions ar
          ON ar.transcription_id = t.id
         AND ar.is_active = 1
         AND ar.status = 'approved'
        ORDER BY t.created_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    results = cursor.fetchall()
    conn.close()
    return results


def delete_transcription(transcription_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM transcription_revisions WHERE transcription_id = ?",
        (transcription_id,),
    )
    cursor.execute("DELETE FROM transcriptions WHERE id = ?", (transcription_id,))
    conn.commit()
    conn.close()

    try:
        from core.rag_bridge import on_transcription_deleted

        on_transcription_deleted(transcription_id)
    except Exception:
        pass


def get_transcription_stats():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(COALESCE(ar.word_count, t.word_count)) AS total_words,
            SUM(t.duration_seconds) AS total_duration,
            AVG(COALESCE(ar.word_count, t.word_count)) AS avg_words
        FROM transcriptions t
        LEFT JOIN transcription_revisions ar
          ON ar.transcription_id = t.id
         AND ar.is_active = 1
         AND ar.status = 'approved'
        """
    )
    result = cursor.fetchone()
    conn.close()
    return {
        "total_transcriptions": result[0] or 0,
        "total_words": result[1] or 0,
        "total_duration_hours": (result[2] or 0) / 3600,
        "avg_words_per_video": result[3] or 0,
    }


def add_history(
    video_id,
    status,
    error_message=None,
    output_file=None,
    audio_path=None,
    video_path=None,
    processing_time_seconds=None,
):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO history
        (video_id, status, error_message, output_file, audio_path, video_path, processing_time_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video_id,
            status,
            error_message,
            output_file,
            to_storage_path(audio_path),
            to_storage_path(video_path),
            processing_time_seconds,
        ),
    )
    conn.commit()
    conn.close()


def get_history(limit=50):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT h.id, v.url, v.title, h.status, h.output_file, h.audio_path, h.video_path, h.created_at
        FROM history h
        LEFT JOIN videos v ON h.video_id = v.id
        ORDER BY h.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    results = cursor.fetchall()
    conn.close()
    return [
        (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            from_storage_path(row[5]) if row[5] else None,
            from_storage_path(row[6]) if row[6] else None,
            row[7],
        )
        for row in results
    ]


def clear_history():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    conn.commit()
    conn.close()


def add_queue_item(url, priority=0, status="pending"):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO queue (url, priority, status)
        VALUES (?, ?, ?)
        """,
        (url, priority, status),
    )
    queue_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return queue_id


def get_queue_items(statuses=None):
    conn = _connect()
    cursor = conn.cursor()
    sql = "SELECT id, url, priority, status, retry_count, added_at FROM queue"
    params = []
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        sql += f" WHERE status IN ({placeholders})"
        params.extend(statuses)
    sql += " ORDER BY added_at ASC, priority DESC"
    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    return results


def update_queue_status(queue_id, status):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE queue SET status = ? WHERE id = ?",
        (status, queue_id),
    )
    conn.commit()
    conn.close()


def increment_queue_retry(queue_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE queue SET retry_count = retry_count + 1 WHERE id = ?",
        (queue_id,),
    )
    conn.commit()
    conn.close()


def remove_queue_item(queue_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM queue WHERE id = ?", (queue_id,))
    conn.commit()
    conn.close()


def clear_queue():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM queue")
    conn.commit()
    conn.close()


def search_history(query=None, status=None, date_from=None, date_to=None, limit=50):
    conn = _connect()
    cursor = conn.cursor()

    sql = (
        "SELECT h.id, v.url, v.title, h.status, h.output_file, h.audio_path, h.video_path, h.created_at, h.error_message "
        "FROM history h LEFT JOIN videos v ON h.video_id = v.id WHERE 1=1"
    )
    params = []

    if query:
        sql += " AND (v.title LIKE ? OR v.url LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])

    if status:
        sql += " AND h.status = ?"
        params.append(status)

    if date_from:
        sql += " AND h.created_at >= ?"
        params.append(date_from)

    if date_to:
        sql += " AND h.created_at <= ?"
        params.append(date_to)

    sql += " ORDER BY h.created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    results = cursor.fetchall()
    conn.close()
    return [
        (
            row[0],
            row[1],
            row[2],
            row[3],
            row[4],
            from_storage_path(row[5]) if row[5] else None,
            from_storage_path(row[6]) if row[6] else None,
            row[7],
            row[8],
        )
        for row in results
    ]


def create_chat_session(transcription_id, title):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_sessions (transcription_id, title) VALUES (?, ?)",
        (transcription_id, title),
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id


def get_chat_sessions(transcription_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, created_at FROM chat_sessions WHERE transcription_id = ? ORDER BY created_at DESC",
        (transcription_id,),
    )
    results = cursor.fetchall()
    conn.close()
    return results


def delete_chat_session(session_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def add_chat_message(session_id, role, content):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    conn.commit()
    conn.close()


def get_chat_history(session_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, created_at FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    results = cursor.fetchall()
    conn.close()
    return results


# =============================================================================
# TRANSCRIPTION USED FLAG
# =============================================================================

def toggle_transcription_used(transcription_id, is_used=None):
    """
    Toggle or set the is_used flag for a transcription.
    
    Args:
        transcription_id: ID of the transcription
        is_used: If None, toggle. If True/False, set explicitly.
    
    Returns:
        New is_used value (0 or 1)
    """
    conn = _connect()
    cursor = conn.cursor()
    
    if is_used is None:
        # Toggle: get current value and flip
        cursor.execute(
            "SELECT is_used FROM transcriptions WHERE id = ?",
            (transcription_id,)
        )
        row = cursor.fetchone()
        current = row[0] if row and row[0] else 0
        new_value = 0 if current else 1
    else:
        new_value = 1 if is_used else 0
    
    cursor.execute(
        "UPDATE transcriptions SET is_used = ? WHERE id = ?",
        (new_value, transcription_id)
    )
    conn.commit()
    conn.close()
    return new_value


def get_transcription_used_status(transcription_id):
    """Get the is_used status of a transcription."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_used FROM transcriptions WHERE id = ?",
        (transcription_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row and row[0] else False


def get_used_transcriptions_count():
    """Get count of transcriptions marked as used."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transcriptions WHERE is_used = 1")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def mark_all_transcriptions_unused():
    """Reset all transcriptions to unused."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE transcriptions SET is_used = 0")
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected


# --- Application jobs (app layer / API / CLI) ---

def insert_job(
    job_id,
    input_type,
    input_value,
    status="queued",
    expanded_count=0,
    progress_json=None,
    log_tail=None,
    options_json=None,
):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (
            id, status, input_type, input_value, expanded_count,
            progress_json, log_tail, created_at, options_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            status,
            input_type,
            input_value,
            expanded_count,
            progress_json,
            log_tail,
            datetime.now(),
            options_json,
        ),
    )
    conn.commit()
    conn.close()
    return job_id


def get_job_row(job_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, status, input_type, input_value, expanded_count,
               progress_json, log_tail, error_message,
               result_transcription_id, result_video_id,
               created_at, started_at, finished_at, result_json,
               worker_id, heartbeat_at, options_json
        FROM jobs WHERE id = ?
        """,
        (job_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def list_job_rows(status=None, limit=50):
    conn = _connect()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            """
            SELECT id, status, input_type, input_value, expanded_count,
                   progress_json, log_tail, error_message,
                   result_transcription_id, result_video_id,
                   created_at, started_at, finished_at, result_json,
                   worker_id, heartbeat_at, options_json
            FROM jobs WHERE status = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (status, limit),
        )
    else:
        cursor.execute(
            """
            SELECT id, status, input_type, input_value, expanded_count,
                   progress_json, log_tail, error_message,
                   result_transcription_id, result_video_id,
                   created_at, started_at, finished_at, result_json,
                   worker_id, heartbeat_at, options_json
            FROM jobs
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def update_job_fields(job_id, **fields):
    if not fields:
        return
    allowed = {
        "status",
        "expanded_count",
        "progress_json",
        "log_tail",
        "error_message",
        "result_transcription_id",
        "result_video_id",
        "result_json",
        "worker_id",
        "heartbeat_at",
        "started_at",
        "finished_at",
        "options_json",
    }
    cols = []
    vals = []
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Invalid job field: {key}")
        cols.append(f"{key} = ?")
        vals.append(value)
    vals.append(job_id)
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE jobs SET {', '.join(cols)} WHERE id = ?",
        vals,
    )
    conn.commit()
    conn.close()


def get_next_queued_job_id():
    """Peek next queued id (non-claiming). Prefer claim_next_queued_job()."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id FROM jobs
        WHERE status = 'queued'
        ORDER BY created_at ASC
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def claim_next_queued_job(worker_id=None):
    """Atomically transition the oldest queued job to running.

    Returns job_id or None. Uses BEGIN IMMEDIATE so concurrent workers
    cannot claim the same row.
    """
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            conn.commit()
            return None
        job_id = row[0]
        owner = str(worker_id or "legacy-worker")
        now = datetime.now()
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'running',
                started_at = ?,
                worker_id = ?,
                heartbeat_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, owner, now, job_id),
        )
        if cursor.rowcount != 1:
            conn.commit()
            return None
        conn.commit()
        return job_id
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def touch_job_heartbeat(job_id, worker_id):
    """Renew one running job lease only when owned by this worker."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE jobs
        SET heartbeat_at = ?
        WHERE id = ? AND status = 'running' AND worker_id = ?
        """,
        (datetime.now(), job_id, str(worker_id)),
    )
    updated = cursor.rowcount == 1
    conn.commit()
    conn.close()
    return updated


def fail_orphan_running_jobs(error_message=None, stale_after_seconds=120):
    """Mark only missing or expired running leases as failed.

    Returns list of failed job ids.
    """
    msg = error_message or (
        "Job interrupted: worker process restarted while status was running"
    )
    conn = _connect()
    cursor = conn.cursor()
    cutoff = datetime.now() - timedelta(seconds=max(0, int(stale_after_seconds)))
    cursor.execute(
        """
        SELECT id FROM jobs
        WHERE status = 'running'
          AND (heartbeat_at IS NULL OR heartbeat_at < ?)
        """,
        (cutoff,),
    )
    ids = [r[0] for r in cursor.fetchall()]
    now = datetime.now()
    for job_id in ids:
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                finished_at = ?,
                error_message = ?,
                log_tail = COALESCE(log_tail, '') || ?,
                worker_id = NULL,
                heartbeat_at = NULL
            WHERE id = ? AND status = 'running'
            """,
            (
                now,
                msg,
                f"\n[recovery] {msg}\n",
                job_id,
            ),
        )
    conn.commit()
    conn.close()
    return ids


def count_jobs_by_status(status):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,))
    n = cursor.fetchone()[0]
    conn.close()
    return n


# --- RAG index queue (transactional) ---

def enqueue_rag_job(transcription_id, op="index"):
    """Insert a queued RAG job. Concurrent enqueues never overwrite others."""
    conn = _connect()
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute(
        """
        INSERT INTO rag_index_jobs
            (transcription_id, op, status, attempts, created_at, updated_at)
        VALUES (?, ?, 'queued', 0, ?, ?)
        """,
        (int(transcription_id), op or "index", now, now),
    )
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return job_id


def claim_next_rag_job(stale_running_seconds=900, max_attempts=3):
    """Recover expired running jobs, then atomically claim one queued/error job.

    Returns dict row or None.
    """
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.cursor()
        now = datetime.now()
        # Recover stale running → queued (retry without loss)
        cursor.execute(
            """
            UPDATE rag_index_jobs
            SET status = 'queued',
                last_error = COALESCE(last_error, '') || ' [recovered stale running]',
                claimed_at = NULL,
                next_attempt_at = NULL,
                updated_at = ?
            WHERE status = 'running'
              AND claimed_at IS NOT NULL
              AND (
                    CAST(strftime('%s', ?) AS INTEGER)
                  - CAST(strftime('%s', claimed_at) AS INTEGER)
              ) > ?
            """,
            (now, now, int(stale_running_seconds)),
        )
        # Also recover running with null claimed_at
        cursor.execute(
            """
            UPDATE rag_index_jobs
            SET status = 'queued',
                last_error = COALESCE(last_error, '') || ' [recovered orphan running]',
                claimed_at = NULL,
                next_attempt_at = NULL,
                updated_at = ?
            WHERE status = 'running' AND claimed_at IS NULL
            """,
            (now,),
        )
        cursor.execute(
            """
            SELECT id, transcription_id, op, status, attempts, last_error, last_result,
                   claimed_at, created_at, updated_at, next_attempt_at
            FROM rag_index_jobs
            WHERE status = 'queued'
               OR (
                    status = 'error'
                    AND attempts < ?
                    AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
               )
            ORDER BY
                CASE WHEN status = 'queued' THEN 0 ELSE 1 END,
                COALESCE(next_attempt_at, created_at) ASC,
                created_at ASC
            LIMIT 1
            """
            ,
            (int(max_attempts), now),
        )
        row = cursor.fetchone()
        if not row:
            conn.commit()
            return None
        job_id = row[0]
        cursor.execute(
            """
            UPDATE rag_index_jobs
            SET status = 'running',
                attempts = attempts + 1,
                claimed_at = ?,
                updated_at = ?
            WHERE id = ? AND status IN ('queued', 'error')
            """,
            (now, now, job_id),
        )
        if cursor.rowcount != 1:
            conn.commit()
            return None
        cursor.execute(
            """
            SELECT id, transcription_id, op, status, attempts, last_error, last_result,
                   claimed_at, created_at, updated_at, next_attempt_at
            FROM rag_index_jobs WHERE id = ?
            """,
            (job_id,),
        )
        claimed = cursor.fetchone()
        conn.commit()
        if not claimed:
            return None
        return {
            "id": claimed[0],
            "transcription_id": claimed[1],
            "op": claimed[2],
            "status": claimed[3],
            "attempts": claimed[4],
            "last_error": claimed[5],
            "last_result": claimed[6],
            "claimed_at": claimed[7],
            "created_at": claimed[8],
            "updated_at": claimed[9],
            "next_attempt_at": claimed[10],
        }
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def finish_rag_job(
    job_id,
    *,
    status,
    last_error=None,
    last_result=None,
    retry_delay_seconds=0,
):
    conn = _connect()
    cursor = conn.cursor()
    now = datetime.now()
    next_attempt_at = None
    if status == "error" and retry_delay_seconds > 0:
        next_attempt_at = now + timedelta(seconds=int(retry_delay_seconds))
    cursor.execute(
        """
        UPDATE rag_index_jobs
        SET status = ?,
            last_error = ?,
            last_result = ?,
            updated_at = ?,
            claimed_at = CASE WHEN ? = 'running' THEN claimed_at ELSE NULL END,
            next_attempt_at = ?
        WHERE id = ?
        """,
        (
            status,
            last_error,
            last_result,
            now,
            status,
            next_attempt_at,
            int(job_id),
        ),
    )
    conn.commit()
    conn.close()


def count_rag_jobs_by_status(status):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM rag_index_jobs WHERE status = ?",
        (status,),
    )
    n = cursor.fetchone()[0]
    conn.close()
    return n


def list_rag_job_rows(status=None, limit=100):
    conn = _connect()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            """
            SELECT id, transcription_id, op, status, attempts, last_error, last_result,
                   claimed_at, created_at, updated_at, next_attempt_at
            FROM rag_index_jobs WHERE status = ?
            ORDER BY created_at ASC LIMIT ?
            """,
            (status, limit),
        )
    else:
        cursor.execute(
            """
            SELECT id, transcription_id, op, status, attempts, last_error, last_result,
                   claimed_at, created_at, updated_at, next_attempt_at
            FROM rag_index_jobs
            ORDER BY created_at ASC LIMIT ?
            """,
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows


def import_legacy_rag_jsonl_once(queue_file, setting_key="rag_queue_jsonl_imported"):
    """Idempotently import pending/error jobs from legacy JSONL into SQLite.

    Preserves corpus/manifest/RAG DB (only reads JSONL queue). Returns import count.
    """
    flag = get_setting(setting_key)
    if flag == "1":
        return 0
    path = Path(queue_file) if queue_file else None
    imported = 0
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                job = json.loads(line)
            except json.JSONDecodeError:
                continue
            status = str(job.get("status") or "pending").lower()
            if status not in {"pending", "error", "queued"}:
                continue
            tid = job.get("transcription_id")
            if tid is None:
                continue
            op = job.get("op") or "index"
            # Map pending → queued
            target_status = "error" if status == "error" else "queued"
            conn = _connect()
            cursor = conn.cursor()
            # Idempotent: skip if same tid+op already queued/error/running
            cursor.execute(
                """
                SELECT id FROM rag_index_jobs
                WHERE transcription_id = ? AND op = ?
                  AND status IN ('queued', 'error', 'running')
                LIMIT 1
                """,
                (int(tid), op),
            )
            if cursor.fetchone():
                conn.close()
                continue
            now = datetime.now()
            cursor.execute(
                """
                INSERT INTO rag_index_jobs
                    (transcription_id, op, status, attempts, last_error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(tid),
                    op,
                    target_status,
                    int(job.get("attempts") or 0),
                    job.get("last_error"),
                    now,
                    now,
                ),
            )
            conn.commit()
            conn.close()
            imported += 1
    set_setting(setting_key, "1")
    return imported
