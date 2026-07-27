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


def _print_progress(message):
    if isinstance(message, str):
        print(message)


def create_worker():
    from core.worker import TranscriberWorker

    return TranscriberWorker(
        log_callback=print,
        progress_callback=_print_progress,
        complete_callback=None,
        confirm_callback=lambda _title, _message: False,
    )


def run_cli(urls):
    from database import init_database
    from core.url_resolver import expand_input_urls

    init_database()
    # Expand playlists before processing; each job remains a single video
    expanded = expand_input_urls(urls, expand_watch_list=False, logger=print)
    if len(expanded) != len(urls):
        print(f"Playlist(s) expandida(s): {len(urls)} entrada(s) → {len(expanded)} video(s)")
    worker = create_worker()
    summary = worker.processar_lista(expanded)
    if summary.get("cancelled") or summary.get("failed", 0) > 0:
        return 1
    return 0


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
