from __future__ import annotations

import io
import json
import urllib.error

import pytest

from core.ollama_client import OllamaClient, OllamaClientError


SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_chat_json_returns_validated_data_and_usage(monkeypatch):
    envelope = {
        "message": {"content": json.dumps({"value": "ok"})},
        "prompt_eval_count": 12,
        "eval_count": 4,
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _req, timeout: FakeResponse(envelope),
    )

    result = OllamaClient(url="http://ollama", model="phi4-mini").chat_json(
        [{"role": "user", "content": "x"}],
        SCHEMA,
        options={"temperature": 0},
    )

    assert result["data"] == {"value": "ok"}
    assert result["usage"]["prompt_eval_count"] == 12


def test_chat_json_rejects_invalid_content_json(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _req, timeout: FakeResponse({"message": {"content": "not-json"}}),
    )

    with pytest.raises(OllamaClientError, match="não é JSON"):
        OllamaClient(url="http://ollama", model="phi4-mini").chat_json([], SCHEMA)


def test_chat_json_rejects_schema_mismatch(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda _req, timeout: FakeResponse(
            {"message": {"content": json.dumps({"other": "x"})}}
        ),
    )

    with pytest.raises(OllamaClientError, match="obrigatório"):
        OllamaClient(url="http://ollama", model="phi4-mini").chat_json([], SCHEMA)


def test_chat_json_surfaces_http_error(monkeypatch):
    def fail(_req, timeout):
        raise urllib.error.HTTPError(
            "http://ollama/api/chat",
            404,
            "not found",
            {},
            io.BytesIO(b'{"error":"model not found"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(OllamaClientError, match="404.*model not found"):
        OllamaClient(url="http://ollama", model="missing").chat_json([], SCHEMA)


def test_chat_json_surfaces_timeout(monkeypatch):
    def fail(_req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(OllamaClientError, match="timeout de 7s"):
        OllamaClient(url="http://ollama", model="phi4-mini").chat_json(
            [], SCHEMA, timeout=7
        )
