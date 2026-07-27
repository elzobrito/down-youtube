import main


class DummyWorker:
    seen_urls = None
    summary = {"success": 1, "failed": 0, "skipped": 0, "cancelled": False}

    def __init__(self, **_kwargs):
        pass

    def processar_lista(self, urls):
        type(self).seen_urls = list(urls)
        return dict(type(self).summary)


def test_collects_positional_url():
    args = main.build_parser().parse_args(["https://www.youtube.com/watch?v=abc"])

    assert main.collect_urls(args) == ["https://www.youtube.com/watch?v=abc"]


def test_collects_url_option_and_urls_file(tmp_path):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(
        "# comentario\nhttps://www.youtube.com/watch?v=file\n\n",
        encoding="utf-8",
    )
    args = main.build_parser().parse_args(
        [
            "--url",
            "https://www.youtube.com/watch?v=flag",
            "--urls",
            str(urls_file),
        ]
    )

    assert main.collect_urls(args) == [
        "https://www.youtube.com/watch?v=flag",
        "https://www.youtube.com/watch?v=file",
    ]


def test_main_uses_cli_when_urls_are_provided(monkeypatch):
    called = {}

    def fake_run_cli(urls):
        called["urls"] = urls
        return 0

    monkeypatch.setattr(main, "run_cli", fake_run_cli)
    monkeypatch.setattr(
        "sys.argv",
        ["main.py", "https://www.youtube.com/watch?v=abc"],
    )

    assert main.main() == 0
    assert called["urls"] == ["https://www.youtube.com/watch?v=abc"]


def test_run_cli_returns_nonzero_when_processing_fails(monkeypatch):
    class FakeJob:
        status = "failed"
        error_message = "boom"

    seen = {}

    def fake_create_job(**kwargs):
        seen["kwargs"] = kwargs
        return "job-1"

    def fake_wait_job(jid):
        seen["jid"] = jid
        return FakeJob()

    monkeypatch.setattr("database.init_database", lambda: None)
    monkeypatch.setattr("app.jobs.create_job", fake_create_job)
    monkeypatch.setattr("app.jobs.wait_job", fake_wait_job)

    assert main.run_cli(["https://www.youtube.com/watch?v=abc"]) == 1
    assert seen["kwargs"]["url"] == "https://www.youtube.com/watch?v=abc"
    assert seen["jid"] == "job-1"
