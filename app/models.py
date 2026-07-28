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
    input_type: str  # url | local | batch
    input_value: str
    expanded_count: int = 0
    progress: Optional[Dict[str, Any]] = None
    log_tail: str = ""
    error_message: Optional[str] = None
    result_transcription_id: Optional[int] = None
    result_video_id: Optional[int] = None
    results: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    options: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        for key in ("created_at", "started_at", "finished_at"):
            val = data.get(key)
            if isinstance(val, datetime):
                data[key] = val.isoformat()
        return data


def job_from_row(row) -> Job:
    """Map database row (tuple) to Job.

    Columns:
      0 id, 1 status, 2 input_type, 3 input_value, 4 expanded_count,
      5 progress_json, 6 log_tail, 7 error_message,
      8 result_transcription_id, 9 result_video_id,
      10 created_at, 11 started_at, 12 finished_at, 13 result_json (optional),
      14 worker_id, 15 heartbeat_at, 16 options_json (optional)
    """
    import json

    progress = None
    if row[5]:
        try:
            progress = json.loads(row[5])
        except Exception:
            progress = {"raw": row[5]}

    results = None
    if len(row) > 13 and row[13]:
        try:
            parsed = json.loads(row[13])
            if isinstance(parsed, list):
                results = parsed
        except Exception:
            results = None

    options = None
    if len(row) > 16 and row[16]:
        try:
            parsed_opts = json.loads(row[16])
            if isinstance(parsed_opts, dict):
                options = parsed_opts
        except Exception:
            options = None
    # Legacy jobs without options_json → treat as off (snapshot migration)
    if options is None:
        options = {"asr_audio_preprocess": "off"}

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
        results=results,
        created_at=row[10],
        started_at=row[11],
        finished_at=row[12],
        options=options,
    )
