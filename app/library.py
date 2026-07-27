"""Library facade for CLI/API (read models over transcriptions)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import (
    get_all_transcriptions,
    get_transcription,
    get_transcription_stats,
    init_database,
    search_transcriptions,
)


def list_transcriptions(
    *,
    query: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    init_database()
    if query:
        rows = search_transcriptions(query)
    else:
        rows = get_all_transcriptions(limit=limit, offset=offset)

    out: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        # get_all: id, title, channel, lang, words, duration, created, is_used
        if len(row) >= 8:
            out.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "channel": row[2],
                    "language": row[3],
                    "word_count": row[4],
                    "duration": row[5],
                    "created_at": str(row[6]) if row[6] is not None else None,
                    "is_used": bool(row[7]),
                }
            )
        elif len(row) >= 1:
            out.append({"id": row[0], "raw": list(row)})
    return out


def get_transcription_detail(transcription_id: int) -> Optional[Dict[str, Any]]:
    init_database()
    t = get_transcription(transcription_id)
    if not t:
        return None
    # Flexible mapping depending on get_transcription shape
    if isinstance(t, dict):
        return t
    if isinstance(t, (list, tuple)):
        return {
            "id": transcription_id,
            "fields": list(t),
            "full_text": t[3] if len(t) > 3 else None,
        }
    return {"id": transcription_id, "data": t}


def library_stats() -> Dict[str, Any]:
    init_database()
    return get_transcription_stats()
