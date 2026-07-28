"""Job queue and worker bridge (application layer)."""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.models import Job, job_from_row
from database import (
    count_jobs_by_status,
    get_job_row,
    get_next_queued_job_id,
    init_database,
    insert_job,
    list_job_rows,
    update_job_fields,
)

LOG_TAIL_MAX_CHARS = 12000

_lock = threading.RLock()
_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_active_worker = None  # TranscriberWorker instance while running
_process_fn: Optional[Callable[[Job], Dict[str, Any]]] = None
# Per-job hooks for GUI (confirm dialogs, queue row updates)
_job_hooks: Dict[str, Dict[str, Any]] = {}


def _ensure_db():
    init_database()


def set_job_hooks(
    job_id: str,
    *,
    confirm_callback: Optional[Callable[[str, str], bool]] = None,
    queue_status_callback: Optional[Callable[[Any, str], None]] = None,
) -> None:
    """Attach GUI callbacks for a job (confirm reprocess, queue status)."""
    with _lock:
        hooks = _job_hooks.setdefault(job_id, {})
        if confirm_callback is not None:
            hooks["confirm"] = confirm_callback
        if queue_status_callback is not None:
            hooks["queue_status"] = queue_status_callback


def clear_job_hooks(job_id: str) -> None:
    with _lock:
        _job_hooks.pop(job_id, None)


def has_active_work() -> bool:
    """True if any job is queued or running."""
    _ensure_db()
    return count_jobs_by_status("running") > 0 or count_jobs_by_status("queued") > 0


def create_job(
    *,
    url: Optional[str] = None,
    path: Optional[str] = None,
    auto_start: bool = True,
) -> str:
    """Enqueue a job. Exactly one of url or path required. Returns job_id."""
    _ensure_db()
    if bool(url) == bool(path):
        raise ValueError("Provide exactly one of url or path")

    if url:
        input_type = "url"
        input_value = url.strip()
        if not input_value:
            raise ValueError("url is empty")
    else:
        input_type = "local"
        input_value = str(Path(path).expanduser())
        if not input_value:
            raise ValueError("path is empty")

    job_id = str(uuid.uuid4())
    insert_job(job_id, input_type, input_value, status="queued")
    if auto_start:
        start_worker_loop()
    return job_id


def create_batch_job(
    items: List[Any],
    *,
    auto_start: bool = True,
    confirm_callback: Optional[Callable[[str, str], bool]] = None,
    queue_status_callback: Optional[Callable[[Any, str], None]] = None,
) -> str:
    """
    Enqueue a batch of items processed by one TranscriberWorker.run.

    Each item may be:
      - str URL
      - (queue_id, url)
      - (queue_id, path_or_url, type) with type in {None, 'url', 'local'}
    """
    _ensure_db()
    if not items:
        raise ValueError("items is empty")

    normalized: List[Any] = []
    for item in items:
        if isinstance(item, (tuple, list)):
            normalized.append(list(item))
        else:
            normalized.append(str(item).strip())

    job_id = str(uuid.uuid4())
    insert_job(
        job_id,
        "batch",
        json.dumps(normalized, default=str),
        status="queued",
        expanded_count=len(normalized),
    )
    if confirm_callback or queue_status_callback:
        set_job_hooks(
            job_id,
            confirm_callback=confirm_callback,
            queue_status_callback=queue_status_callback,
        )
    if auto_start:
        start_worker_loop()
    return job_id


def get_job(job_id: str) -> Optional[Job]:
    _ensure_db()
    row = get_job_row(job_id)
    if not row:
        return None
    return job_from_row(row)


def list_jobs(status: Optional[str] = None, limit: int = 50) -> List[Job]:
    _ensure_db()
    rows = list_job_rows(status=status, limit=limit)
    return [job_from_row(r) for r in rows]


def cancel_job(job_id: str) -> bool:
    """Cancel queued job immediately; request cancel if running."""
    global _active_worker
    _ensure_db()
    job = get_job(job_id)
    if not job:
        return False
    if job.status == "queued":
        update_job_fields(
            job_id,
            status="cancelled",
            finished_at=datetime.now(),
            error_message="Cancelled while queued",
        )
        return True
    if job.status == "running":
        with _lock:
            w = _active_worker
            if w is not None:
                try:
                    w.cancelar()
                except Exception:
                    pass
        update_job_fields(job_id, status="cancelled")  # finalised when worker ends
        return True
    return False


def append_log(job_id: str, line: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    text = (job.log_tail or "") + str(line).rstrip() + "\n"
    if len(text) > LOG_TAIL_MAX_CHARS:
        text = text[-LOG_TAIL_MAX_CHARS:]
    update_job_fields(job_id, log_tail=text)


def update_progress(job_id: str, progress: Dict[str, Any]) -> None:
    """
    Merge progress by stage so polling UI does not lose earlier stage snapshots.

    Stored shape:
      {
        "by_stage": { "download": {...}, "transcription": {...}, ... },
        "last": { ... last raw event ... }
      }
    """
    if not isinstance(progress, dict):
        return
    job = get_job(job_id)
    state: Dict[str, Any] = {"by_stage": {}, "last": progress}
    if job and isinstance(job.progress, dict):
        prev = job.progress
        if "by_stage" in prev and isinstance(prev.get("by_stage"), dict):
            state["by_stage"] = dict(prev["by_stage"])
        elif prev.get("stage"):
            # Migrate flat last-event format
            state["by_stage"] = {str(prev["stage"]): prev}

    stage = progress.get("stage")
    if stage:
        # Keep latest payload per stage key
        state["by_stage"][str(stage)] = progress
    else:
        state["by_stage"]["_raw"] = progress

    update_job_fields(job_id, progress_json=json.dumps(state, default=str))


def set_process_function(fn: Optional[Callable[[Job], Dict[str, Any]]]) -> None:
    """Inject process function (tests). None restores default worker bridge."""
    global _process_fn
    _process_fn = fn


def start_worker_loop() -> None:
    """Ensure background loop is running (idempotent)."""
    global _worker_thread
    with _lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return
        _stop_event.clear()
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="down-youtube-job-worker",
            daemon=True,
        )
        _worker_thread.start()


def stop_worker_loop(timeout: float = 2.0) -> None:
    """Signal loop to stop (daemon; used in tests)."""
    global _worker_thread
    _stop_event.set()
    t = _worker_thread
    if t is not None and t.is_alive():
        t.join(timeout=timeout)
    with _lock:
        _worker_thread = None


def wait_job(job_id: str, timeout: Optional[float] = None, poll: float = 0.25) -> Job:
    """Block until job reaches a terminal state."""
    start_worker_loop()
    deadline = None if timeout is None else time.time() + timeout
    terminal = {"done", "failed", "cancelled"}
    while True:
        job = get_job(job_id)
        if not job:
            raise KeyError(f"job not found: {job_id}")
        if job.status in terminal:
            return job
        if deadline is not None and time.time() >= deadline:
            raise TimeoutError(f"job {job_id} still {job.status}")
        time.sleep(poll)


def _worker_loop() -> None:
    while not _stop_event.is_set():
        if count_jobs_by_status("running") > 0:
            time.sleep(0.2)
            continue
        job_id = get_next_queued_job_id()
        if not job_id:
            # Idle briefly; exit if stop requested
            if _stop_event.wait(0.3):
                break
            continue
        _run_one_job(job_id)


def _run_one_job(job_id: str) -> None:
    global _active_worker
    job = get_job(job_id)
    if not job or job.status != "queued":
        return

    update_job_fields(
        job_id,
        status="running",
        started_at=datetime.now(),
    )
    append_log(job_id, f"Job started ({job.input_type})")

    try:
        process = _process_fn or _default_process_job
        result = process(job)
        # Re-read: may have been cancelled
        current = get_job(job_id)
        if current and current.status == "cancelled":
            update_job_fields(
                job_id,
                finished_at=datetime.now(),
                error_message=current.error_message or "Cancelled",
            )
            append_log(job_id, "Job cancelled")
            return

        status = result.get("status", "done")
        fields: Dict[str, Any] = {
            "status": status,
            "finished_at": datetime.now(),
            "expanded_count": result.get("expanded_count", 0),
        }
        if result.get("error_message"):
            fields["error_message"] = result["error_message"]
        if result.get("result_transcription_id") is not None:
            fields["result_transcription_id"] = result["result_transcription_id"]
        if result.get("result_video_id") is not None:
            fields["result_video_id"] = result["result_video_id"]
        update_job_fields(job_id, **fields)
        append_log(job_id, f"Job finished: {status}")
    except Exception as exc:
        update_job_fields(
            job_id,
            status="failed",
            finished_at=datetime.now(),
            error_message=str(exc),
        )
        append_log(job_id, f"Job error: {exc}")
    finally:
        with _lock:
            _active_worker = None


def _default_process_job(job: Job) -> Dict[str, Any]:
    """Run TranscriberWorker for this job (hooks optional for GUI)."""
    global _active_worker
    from core.worker import TranscriberWorker
    from core.url_resolver import expand_input_urls
    from database import get_latest_transcription_for_source

    with _lock:
        hooks = dict(_job_hooks.get(job.id) or {})

    confirm_cb = hooks.get("confirm") or (lambda _t, _m: False)
    queue_status_cb = hooks.get("queue_status")

    def log_cb(msg):
        append_log(job.id, str(msg))

    def progress_cb(data):
        if isinstance(data, dict):
            update_progress(job.id, data)
        else:
            update_progress(job.id, {"message": str(data)})

    def complete_cb(*_args, **_kwargs):
        pass

    worker = TranscriberWorker(
        log_callback=log_cb,
        progress_callback=progress_cb,
        complete_callback=complete_cb,
        queue_status_callback=queue_status_cb,
        confirm_callback=confirm_cb,
    )
    with _lock:
        _active_worker = worker

    if job.input_type == "local":
        items: List[Any] = [(None, job.input_value, "local")]
        expanded_count = 1
    elif job.input_type == "batch":
        try:
            raw_items = json.loads(job.input_value)
        except Exception as exc:
            return {
                "status": "failed",
                "expanded_count": 0,
                "error_message": f"Invalid batch payload: {exc}",
            }
        # Expand any plain URL strings; keep queue tuples as worker expects
        items = []
        for it in raw_items:
            if isinstance(it, list):
                items.append(tuple(it))
            else:
                items.append(it)
        # Expand playlists inside worker via processar_lista (expand_watch_list=False)
        expanded_count = len(items)
        update_job_fields(job.id, expanded_count=expanded_count)
    else:
        expanded = expand_input_urls([job.input_value], logger=log_cb)
        items = expanded
        expanded_count = len(expanded)
        update_job_fields(job.id, expanded_count=expanded_count)

    current = get_job(job.id)
    if current and current.status == "cancelled":
        clear_job_hooks(job.id)
        return {"status": "cancelled", "expanded_count": expanded_count}

    summary = worker.processar_lista(items)

    if worker.cancel_requested or (get_job(job.id) and get_job(job.id).status == "cancelled"):
        clear_job_hooks(job.id)
        return {
            "status": "cancelled",
            "expanded_count": expanded_count,
            "error_message": "Cancelled by user",
        }

    failed = summary.get("failed", 0) if isinstance(summary, dict) else 0
    cancelled = summary.get("cancelled") if isinstance(summary, dict) else False
    if cancelled:
        clear_job_hooks(job.id)
        return {
            "status": "cancelled",
            "expanded_count": expanded_count,
            "error_message": "Cancelled",
        }
    if failed and (
        not isinstance(summary, dict)
        or summary.get("sucesso", summary.get("success", 0)) == 0
    ):
        err = worker.last_error or "Processing failed"
        clear_job_hooks(job.id)
        return {
            "status": "failed",
            "expanded_count": expanded_count,
            "error_message": err,
        }

    result_tid = None
    result_vid = None
    try:
        if job.input_type == "url":
            row = get_latest_transcription_for_source(url=job.input_value)
            if row and isinstance(row, (list, tuple)) and len(row) >= 1:
                result_tid = row[0] if isinstance(row[0], int) else None
    except Exception:
        pass

    clear_job_hooks(job.id)
    return {
        "status": "done",
        "expanded_count": expanded_count,
        "result_transcription_id": result_tid,
        "result_video_id": result_vid,
    }
