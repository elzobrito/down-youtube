"""CLI: jobs, library, serve — shared application layer."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="down-youtube",
        description="YouTube Transcriber CLI (jobs / library / API server)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # jobs
    jobs_p = sub.add_parser("jobs", help="Job queue operations")
    jobs_sub = jobs_p.add_subparsers(dest="jobs_cmd", required=True)

    create_p = jobs_sub.add_parser("create", help="Enqueue URL or local path")
    create_p.add_argument("--url", help="Media URL (YouTube, X/Twitter, etc.)")
    create_p.add_argument("--path", help="Local media file path")
    create_p.add_argument(
        "--wait",
        action="store_true",
        help="Wait until job finishes (sync)",
    )
    create_p.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Seconds to wait when --wait (default: forever)",
    )

    status_p = jobs_sub.add_parser("status", help="Show job status")
    status_p.add_argument("job_id")

    list_p = jobs_sub.add_parser("list", help="List recent jobs")
    list_p.add_argument("--status", help="Filter: queued|running|done|failed|cancelled")
    list_p.add_argument("--limit", type=int, default=20)

    cancel_p = jobs_sub.add_parser("cancel", help="Cancel job")
    cancel_p.add_argument("job_id")

    # library
    lib_p = sub.add_parser("library", help="Transcription library")
    lib_sub = lib_p.add_subparsers(dest="lib_cmd", required=True)
    lib_list = lib_sub.add_parser("list", help="List transcriptions")
    lib_list.add_argument("--query", "-q", help="Search text")
    lib_list.add_argument("--limit", type=int, default=20)

    # serve
    serve_p = sub.add_parser("serve", help="Run HTTP API (FastAPI/uvicorn)")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    serve_p.add_argument("--reload", action="store_true")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    from database import init_database

    init_database()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "jobs":
        return _cmd_jobs(args)
    if args.command == "library":
        return _cmd_library(args)
    if args.command == "serve":
        return _cmd_serve(args)
    parser.error("unknown command")
    return 2


def _cmd_jobs(args) -> int:
    from app.jobs import cancel_job, create_job, get_job, list_jobs, wait_job

    if args.jobs_cmd == "create":
        try:
            jid = create_job(url=args.url, path=args.path, auto_start=True)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(jid)
        if args.wait:
            try:
                job = wait_job(jid, timeout=args.timeout)
            except TimeoutError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(json.dumps(job.to_dict(), indent=2, default=str))
            return 0 if job.status == "done" else 1
        return 0

    if args.jobs_cmd == "status":
        job = get_job(args.job_id)
        if not job:
            print("not found", file=sys.stderr)
            return 1
        print(json.dumps(job.to_dict(), indent=2, default=str))
        return 0 if job.status != "failed" else 1

    if args.jobs_cmd == "list":
        jobs = list_jobs(status=args.status, limit=args.limit)
        for j in jobs:
            print(f"{j.id}\t{j.status}\t{j.input_type}\t{j.input_value[:80]}")
        return 0

    if args.jobs_cmd == "cancel":
        ok = cancel_job(args.job_id)
        print("ok" if ok else "not cancellable")
        return 0 if ok else 1

    return 2


def _cmd_library(args) -> int:
    from app.library import list_transcriptions

    if args.lib_cmd == "list":
        items = list_transcriptions(query=args.query, limit=args.limit)
        print(json.dumps(items, indent=2, default=str))
        return 0
    return 2


def _cmd_serve(args) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "error: install API deps: pip install 'fastapi' 'uvicorn[standard]'",
            file=sys.stderr,
        )
        return 2

    from app.jobs import start_worker_loop

    start_worker_loop()
    print(f"Serving API on http://{args.host}:{args.port} (local-first)", file=sys.stderr)
    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
