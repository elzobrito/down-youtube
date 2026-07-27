import json
import sqlite3
from datetime import datetime
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)"
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
    source_site="youtube",
):
    conn = _connect()
    cursor = conn.cursor()

    if video_id:
        cursor.execute(
            "SELECT id FROM videos WHERE video_id = ? OR url = ?",
            (video_id, url),
        )
    else:
        cursor.execute("SELECT id FROM videos WHERE url = ?", (url,))

    row = cursor.fetchone()
    if row:
        video_db_id = row[0]
        cursor.execute(
            """
            UPDATE videos
            SET title = COALESCE(?, title),
                channel = COALESCE(?, channel),
                duration = COALESCE(?, duration),
                thumbnail_url = COALESCE(?, thumbnail_url),
                audio_path = COALESCE(?, audio_path),
                video_path = COALESCE(?, video_path)
            WHERE id = ?
            """,
            (
                title,
                channel,
                duration,
                thumbnail_url,
                to_storage_path(audio_path),
                to_storage_path(video_path),
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
                source_site,
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
        (video_id, language, full_text, segments_json, word_count, duration_seconds, model_used, audio_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (video_id, language, text, segments_json, word_count, duration, model, audio_hash),
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
            t.created_at AS created_at,
            t.updated_at AS updated_at,
            COALESCE(t.is_used, 0) AS is_used,
            v.title AS video_title,
            v.url AS video_url,
            v.channel AS channel,
            v.video_id AS youtube_video_id,
            v.audio_path AS audio_path,
            v.video_path AS video_path
        FROM transcriptions t
        JOIN videos v ON t.video_id = v.id
        WHERE t.id = ?
        """,
        (transcription_id,),
    )

    result = cursor.fetchone()
    conn.close()

    if result:
        segments_raw = result["segments_json"]
        return {
            "id": result["id"],
            "video_id": result["video_id"],
            "language": result["language"],
            "full_text": result["full_text"],
            "segments": json.loads(segments_raw) if segments_raw else None,
            "word_count": result["word_count"],
            "duration": result["duration_seconds"],
            "model": result["model_used"],
            "audio_hash": result["audio_hash"],
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


def get_latest_transcription_for_source(video_id=None, url=None):
    conn = _connect()
    cursor = conn.cursor()

    if video_id:
        cursor.execute(
            """
            SELECT t.id, t.created_at
            FROM transcriptions t
            JOIN videos v ON t.video_id = v.id
            WHERE v.video_id = ?
            ORDER BY t.created_at DESC
            LIMIT 1
            """,
            (video_id,),
        )
    elif url:
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
        SELECT t.id, t.video_id, v.title, v.channel, t.word_count, t.language, t.created_at,
               substr(t.full_text, max(1, instr(lower(t.full_text), lower(?)) - 50), 150)
               AS snippet
        FROM transcriptions t
        JOIN videos v ON t.video_id = v.id
        WHERE t.full_text LIKE ?
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
        SELECT t.id, v.title, v.channel, t.language, t.word_count,
               t.duration_seconds, t.created_at, COALESCE(t.is_used, 0)
        FROM transcriptions t
        JOIN videos v ON t.video_id = v.id
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
            SUM(word_count) AS total_words,
            SUM(duration_seconds) AS total_duration,
            AVG(word_count) AS avg_words
        FROM transcriptions
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
):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (
            id, status, input_type, input_value, expanded_count,
            progress_json, log_tail, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
               created_at, started_at, finished_at
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
                   created_at, started_at, finished_at
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
                   created_at, started_at, finished_at
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
        "started_at",
        "finished_at",
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


def count_jobs_by_status(status):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,))
    n = cursor.fetchone()[0]
    conn.close()
    return n
