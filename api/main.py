"""FastAPI application factory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from api.deps import require_api_token
from app.jobs import cancel_job, create_job, get_job, list_jobs, start_worker_loop
from app.library import get_transcription_detail, list_transcriptions
from database import get_transcription, init_database


class JobCreate(BaseModel):
    url: Optional[str] = None
    path: Optional[str] = None

    @model_validator(mode="after")
    def one_of(self):
        if bool(self.url) == bool(self.path):
            raise ValueError("Provide exactly one of url or path")
        return self


def create_app() -> FastAPI:
    app = FastAPI(
        title="YouTube Transcriber API",
        version="1.0.0",
        description="Jobs and library API over the shared application layer.",
    )

    @app.on_event("startup")
    def _startup():
        init_database()
        start_worker_loop()

    @app.get("/v1/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/jobs", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_api_token)])
    def post_job(body: JobCreate):
        try:
            jid = create_job(url=body.url, path=body.path, auto_start=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"job_id": jid, "status": "queued"}

    @app.get("/v1/jobs", dependencies=[Depends(require_api_token)])
    def get_jobs(
        status_filter: Optional[str] = Query(None, alias="status"),
        limit: int = Query(50, ge=1, le=200),
    ):
        jobs = list_jobs(status=status_filter, limit=limit)
        return {"jobs": [j.to_dict() for j in jobs]}

    @app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_api_token)])
    def get_job_route(job_id: str):
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job.to_dict()

    @app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(require_api_token)])
    def cancel_job_route(job_id: str):
        ok = cancel_job(job_id)
        if not ok:
            raise HTTPException(status_code=400, detail="not cancellable or not found")
        job = get_job(job_id)
        return {"ok": True, "job": job.to_dict() if job else None}

    @app.get("/v1/jobs/{job_id}/transcript", dependencies=[Depends(require_api_token)])
    def job_transcript(job_id: str):
        job = get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job.status != "done":
            raise HTTPException(
                status_code=409,
                detail=f"job status is {job.status}, not done",
            )
        tid = job.result_transcription_id
        if not tid:
            raise HTTPException(status_code=404, detail="no transcription linked")
        t = get_transcription(tid)
        if not t:
            raise HTTPException(status_code=404, detail="transcription missing")
        # get_transcription returns a tuple/dict depending on version
        if isinstance(t, dict):
            return {"job_id": job_id, "transcription_id": tid, "transcription": t}
        full_text = None
        if isinstance(t, (list, tuple)):
            # best effort: look for long string field
            for cell in t:
                if isinstance(cell, str) and len(cell) > 20:
                    full_text = cell
                    break
        return {
            "job_id": job_id,
            "transcription_id": tid,
            "full_text": full_text,
            "raw": list(t) if isinstance(t, (list, tuple)) else t,
        }

    @app.get("/v1/library", dependencies=[Depends(require_api_token)])
    def library(
        q: Optional[str] = None,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        return {
            "items": list_transcriptions(query=q, limit=limit, offset=offset),
        }

    @app.get("/v1/library/{transcription_id}", dependencies=[Depends(require_api_token)])
    def library_item(transcription_id: int):
        detail = get_transcription_detail(transcription_id)
        if not detail:
            raise HTTPException(status_code=404, detail="not found")
        return detail

    return app


app = create_app()
