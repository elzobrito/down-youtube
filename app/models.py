"""Domain models for the application layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


JOB_STATUSES = frozenset({"queued", "running", "done", "failed", "cancelled"})


@dataclass
class Job:
    id: str
    status: str
    input_type: str  # url | local
    input_value: str
    expanded_count: int = 0
    progress: Optional[Dict[str, Any]] = None
    log_tail: str = ""
    error_message: Optional[str] = None
    result_transcription_id: Optional[int] = None
    result_video_id: Optional[int] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key in ("created_at", "started_at", "finished_at"):
            val = data.get(key)
            if isinstance(val, datetime):
                data[key] = val.isoformat()
        return data


def job_from_row(row) -> Job:
    """Map database row (tuple) to Job."""
    import json

    progress = None
    if row[5]:
        try:
            progress = json.loads(row[5])
        except Exception:
            progress = {"raw": row[5]}

    return Job(
        id=row[0],
        status=row[1],
        input_type=row[2],
        input_value=row[3],
        expanded_count=row[4] or 0,
        progress=progress,
        log_tail=row[6] or "",
        error_message=row[7],
        result_transcription_id=row[8],
        result_video_id=row[9],
        created_at=row[10],
        started_at=row[11],
        finished_at=row[12],
    )
