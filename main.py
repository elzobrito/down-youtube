import argparse
import sys
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(
        description="YouTube Transcriber",
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="URLs do YouTube ou caminhos locais para processar.",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="url_options",
        default=[],
        help="URL do YouTube para processar. Pode ser usado mais de uma vez.",
    )
    parser.add_argument(
        "--urls",
        dest="urls_file",
        help="Arquivo .txt com uma URL por linha.",
    )
    return parser


def collect_urls(args):
    urls = []
    urls.extend(args.urls)
    urls.extend(args.url_options)

    if args.urls_file:
        urls_path = Path(args.urls_file).expanduser()
        with urls_path.open("r", encoding="utf-8") as handle:
            urls.extend(
                line.strip()
                for line in handle
                if line.strip() and not line.lstrip().startswith("#")
            )

    return urls


def run_cli(urls):
    """Process URLs via application layer (create job + wait)."""
    from database import init_database
    from app.jobs import create_job, wait_job
    from pathlib import Path as P

    init_database()
    exit_code = 0
    for raw in urls:
        raw = str(raw).strip()
        if not raw:
            continue
        is_local = P(raw).expanduser().exists() and not raw.startswith("http")
        if is_local:
            jid = create_job(path=raw, auto_start=True)
        else:
            jid = create_job(url=raw, auto_start=True)
        print(f"job {jid} …")
        job = wait_job(jid)
        print(f"  → {job.status}" + (f" ({job.error_message})" if job.error_message else ""))
        if job.status != "done":
            exit_code = 1
    return exit_code


def main():
    parser = build_parser()
    args = parser.parse_args()
    urls = collect_urls(args)

    if urls:
        return run_cli(urls)

    from gui.app import run

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
