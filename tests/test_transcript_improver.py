from __future__ import annotations

import json

import pytest

from core.transcript_improver import (
    TranscriptImprovementCancelled,
    TranscriptImprovementError,
    TranscriptImprover,
    compile_revision,
    normalize_known_terms,
)


class FakeClient:
    def __init__(self, transform=None):
        self.calls = []
        self.transform = transform or (lambda item: item["text"])

    def chat_json(self, messages, schema, **kwargs):
        payload = json.loads(messages[-1]["content"])
        central = [
            item for item in payload["segments"] if not item["context_only"]
        ]
        self.calls.append({"payload": payload, "kwargs": kwargs})
        rows = []
        for item in central:
            corrected = self.transform(item)
            rows.append(
                {
                    "id": item["id"],
                    "corrected_text": corrected,
                    "paragraph_break_after": item["id"].endswith("2"),
                    "remove_as_outtake": "[ERRO]" in item["text"],
                    "outtake_reason": "erro de gravação" if "[ERRO]" in item["text"] else "",
                    "section_title": "Introdução" if item["id"].endswith("1") else "",
                    "commands": [],
                }
            )
        return {
            "data": {"segments": rows},
            "usage": {"prompt_eval_count": 10, "eval_count": 5},
        }


def sample_transcription():
    return {
        "full_text": (
            "A gente instala o calcei e testa no node JTS. "
            "Ele falou sudu rm traco rf barra, mas não execute isso. "
            "[ERRO] nossa, vou gravar de novo."
        ),
        "segments": [
            {
                "start": 0,
                "end": 3,
                "text": "A gente instala o calcei e testa no node JTS.",
            },
            {
                "start": 3,
                "end": 7,
                "text": "Ele falou sudu rm traco rf barra, mas não execute isso.",
            },
            {
                "start": 7,
                "end": 10,
                "text": "[ERRO] nossa, vou gravar de novo.",
            },
        ],
        "video_title": "Linux e SSH",
        "channel": "Canal técnico",
        "language": "pt",
    }


def test_known_terms_and_commands_are_deterministic():
    text = normalize_known_terms(
        "Instale o CalCey no node JTS; sudu rm traco rf barra.",
        context="runtime JavaScript Linux",
    )
    assert "cowsay" in text
    assert "Node.js" in text
    assert "sudo rm -rf /" in text
    assert "sapatos" not in text


def test_chunking_has_context_but_model_returns_only_central_ids():
    segments = TranscriptImprover.normalize_segments(
        "",
        [
            {"start": 0, "end": 1, "text": "a" * 400},
            {"start": 1, "end": 2, "text": "b" * 400},
            {"start": 2, "end": 3, "text": "c" * 400},
        ],
    )
    improver = TranscriptImprover(client=FakeClient(), chunk_chars=500)
    chunks = improver.build_chunks(segments)
    assert len(chunks) == 3
    assert [row["id"] for row in chunks[1]["context"]] == [
        "seg-000001",
        "seg-000003",
    ]


def test_hallucinated_rewrite_is_unselected_and_safe_text_wins():
    def hallucinate(item):
        if "calcei" in item["text"]:
            return "Nós instalamos sapatos e usamos Node.js Spatial Toolkit."
        return item["text"]

    improver = TranscriptImprover(client=FakeClient(hallucinate), chunk_chars=10000)
    result = improver.improve(sample_transcription())

    assert "cowsay" in result["improved_text"]
    assert "Node.js" in result["improved_text"]
    assert "sapatos" not in result["improved_text"]
    unknown = [
        item
        for item in result["proposals"]["proposals"]
        if item["kind"] == "lexical_suggestion"
    ]
    assert unknown
    assert all(not item["selected_by_default"] for item in unknown)
    assert "sudo rm -rf /" in result["improved_text"]
    dangerous = [
        item
        for item in result["proposals"]["proposals"]
        if item.get("dangerous")
    ]
    assert dangerous


def test_outtake_is_removed_from_draft_but_can_be_restored():
    result = TranscriptImprover(
        client=FakeClient(), chunk_chars=10000
    ).improve(sample_transcription())
    assert "vou gravar de novo" not in result["improved_text"]
    outtake = next(
        item
        for item in result["proposals"]["proposals"]
        if item["kind"] == "outtake"
    )
    selected = set(result["decisions"]["selected_proposal_ids"])
    selected.remove(outtake["id"])
    restored = compile_revision(result["proposals"], selected)
    assert "vou gravar de novo" in restored["improved_text"]


def test_missing_segment_ids_retries_then_fills_originals():
    """Empty model output: retry once for quality, then keep originals (no abort)."""

    class BrokenClient(FakeClient):
        def chat_json(self, messages, schema, **kwargs):
            self.calls.append({})
            return {"data": {"segments": []}, "usage": {}}

    client = BrokenClient()
    result = TranscriptImprover(client=client, chunk_chars=10000).improve(
        sample_transcription()
    )
    assert len(client.calls) == 2
    # Draft still produced; source words remain (glossary may normalize terms)
    assert "instala" in result["improved_text"].lower() or "cowsay" in result["improved_text"]
    ids = [item["id"] for item in result["proposals"]["segments"]]
    assert ids == ["seg-000001", "seg-000002", "seg-000003"]


def test_partial_ids_are_aligned_without_abort():
    class PartialClient(FakeClient):
        def chat_json(self, messages, schema, **kwargs):
            payload = json.loads(messages[-1]["content"])
            central = [item for item in payload["segments"] if not item["context_only"]]
            self.calls.append({"payload": payload})
            # Return only the first central id + a bogus extra
            first = central[0]
            return {
                "data": {
                    "segments": [
                        {
                            "id": first["id"],
                            "corrected_text": first["text"],
                            "paragraph_break_after": False,
                            "remove_as_outtake": False,
                            "outtake_reason": "",
                            "section_title": "",
                            "commands": [],
                        },
                        {
                            "id": "seg-999999",
                            "corrected_text": "lixo",
                            "paragraph_break_after": False,
                            "remove_as_outtake": False,
                            "outtake_reason": "",
                            "section_title": "",
                            "commands": [],
                        },
                    ]
                },
                "usage": {},
            }

    client = PartialClient()
    result = TranscriptImprover(client=client, chunk_chars=10000).improve(
        sample_transcription()
    )
    assert len(client.calls) == 1  # partial match → no retry required
    ids = [item["id"] for item in result["proposals"]["segments"]]
    assert ids == ["seg-000001", "seg-000002", "seg-000003"]
    assert "lixo" not in result["improved_text"]


def test_align_chunk_segments_stats():
    central = [
        {"id": "seg-000001", "text": "um"},
        {"id": "seg-000002", "text": "dois"},
    ]
    raw = [{"id": "seg-000002", "corrected_text": "Dois."}]
    aligned, stats = TranscriptImprover.align_chunk_segments(central, raw)
    assert [row["id"] for row in aligned] == ["seg-000001", "seg-000002"]
    assert aligned[0]["corrected_text"] == "um"
    assert aligned[1]["corrected_text"] == "Dois."
    assert stats["matched"] == 1
    assert stats["missing_ids"] == ["seg-000001"]
    assert stats["coverage"] == 0.5


def test_chunking_respects_max_segments():
    segments = TranscriptImprover.normalize_segments(
        "",
        [{"start": i, "end": i + 1, "text": f"seg {i} short"} for i in range(10)],
    )
    improver = TranscriptImprover(
        client=FakeClient(), chunk_chars=100000, max_segments_per_chunk=3
    )
    chunks = improver.build_chunks(segments)
    assert len(chunks) == 4  # 3+3+3+1
    assert all(len(c["central"]) <= 3 for c in chunks)


def test_cancel_before_first_call_does_not_invoke_model():
    client = FakeClient()
    with pytest.raises(TranscriptImprovementCancelled):
        TranscriptImprover(client=client).improve(
            sample_transcription(),
            cancel_check=lambda: True,
        )
    assert client.calls == []


def test_cancel_between_chunks_stops_before_next_model_call():
    client = FakeClient()
    segments = [
        {"start": index, "end": index + 1, "text": letter * 400}
        for index, letter in enumerate(("a", "b", "c"))
    ]
    transcription = {
        "full_text": " ".join(item["text"] for item in segments),
        "segments": segments,
    }

    with pytest.raises(TranscriptImprovementCancelled):
        TranscriptImprover(client=client, chunk_chars=500).improve(
            transcription,
            cancel_check=lambda: len(client.calls) >= 1,
        )
    assert len(client.calls) == 1


def test_multi_chunk_result_has_complete_unique_segment_coverage():
    client = FakeClient()
    segments = [
        {"start": index, "end": index + 1, "text": letter * 400}
        for index, letter in enumerate(("a", "b", "c"))
    ]
    result = TranscriptImprover(client=client, chunk_chars=500).improve(
        {
            "full_text": " ".join(item["text"] for item in segments),
            "segments": segments,
        }
    )
    ids = [item["id"] for item in result["proposals"]["segments"]]
    assert ids == ["seg-000001", "seg-000002", "seg-000003"]
    assert len(ids) == len(set(ids))


def test_plain_text_fallback_has_no_timestamp_segments():
    transcription = {
        "full_text": "Primeira frase. Segunda frase.",
        "segments": None,
    }
    result = TranscriptImprover(client=FakeClient()).improve(transcription)
    assert result["improved_segments"] is None
    assert "Primeira frase" in result["improved_text"]
