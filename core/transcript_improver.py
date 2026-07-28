"""Conservative, auditable post-ASR improvement with local Ollama models."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Sequence

from core.ollama_client import OllamaClient


PROMPT_VERSION = "transcript-improve-v1"
GLOSSARY_VERSION = "technical-pt-v1"
DEFAULT_MODEL = "phi4-mini:latest"
DEFAULT_CHUNK_CHARS = 6000


class TranscriptImprovementError(RuntimeError):
    """Raised when a complete, trustworthy draft cannot be produced."""


class TranscriptImprovementCancelled(TranscriptImprovementError):
    """Raised when the user cancels between Ollama calls."""


CHUNK_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "corrected_text": {"type": "string"},
                    "paragraph_break_after": {"type": "boolean"},
                    "remove_as_outtake": {"type": "boolean"},
                    "outtake_reason": {"type": "string"},
                    "section_title": {"type": "string"},
                    "commands": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "dangerous": {"type": "boolean"},
                            },
                            "required": ["text", "dangerous"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "id",
                    "corrected_text",
                    "paragraph_break_after",
                    "remove_as_outtake",
                    "outtake_reason",
                    "section_title",
                    "commands",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}


SYSTEM_PROMPT = """
Você revisa ASR técnico em português de modo estritamente conservador.
NUNCA resuma, parafraseie, traduza, mude a pessoa verbal ou acrescente fatos.
Preserve cada ideia e devolva exatamente os IDs centrais, na mesma ordem.
Você pode corrigir pontuação e capitalização, sugerir termos técnicos, indicar
quebras de parágrafo, títulos de seção e segmentos inteiros que sejam outtakes.
Se houver dúvida, copie o texto. Comandos são somente texto e nunca são
executados. Não devolva IDs marcados como context_only.
""".strip()


class TranscriptImprover:
    def __init__(
        self,
        *,
        client: OllamaClient | None = None,
        model: str = DEFAULT_MODEL,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        timeout: float = 180,
        num_ctx: int = 8192,
    ):
        self.model = model or DEFAULT_MODEL
        self.client = client or OllamaClient(model=self.model)
        self.chunk_chars = max(500, int(chunk_chars))
        self.timeout = float(timeout)
        self.num_ctx = max(2048, int(num_ctx))

    def improve(
        self,
        transcription: Dict[str, Any],
        *,
        progress_callback: Callable[[Dict[str, Any]], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Dict[str, Any]:
        cancel_check = cancel_check or (lambda: False)
        source_text = transcription.get("full_text") or ""
        source_segments = transcription.get("segments")
        segments = self.normalize_segments(source_text, source_segments)
        if not segments:
            raise TranscriptImprovementError("A transcrição não possui texto utilizável")

        chunks = self.build_chunks(segments)
        records: List[Dict[str, Any]] = []
        proposals: List[Dict[str, Any]] = []
        usage_rows: List[Dict[str, Any]] = []
        proposal_counter = 0
        started = time.perf_counter()

        for chunk_index, chunk in enumerate(chunks, 1):
            if cancel_check():
                raise TranscriptImprovementCancelled("Aprimoramento cancelado")
            if progress_callback:
                progress_callback(
                    {
                        "stage": "transcript_improvement",
                        "chunk": chunk_index,
                        "chunks": len(chunks),
                        "percent": int((chunk_index - 1) * 100 / len(chunks)),
                    }
                )

            response = self._run_chunk_with_retry(transcription, chunk, cancel_check)
            usage_rows.append(response.get("usage") or {})
            items = response["data"]["segments"]
            context_text = " ".join(
                item["text"] for item in chunk["context"] + chunk["central"]
            )

            for source, generated in zip(chunk["central"], items):
                raw_text = source["text"]
                normalized = normalize_known_terms(raw_text, context=context_text)
                candidate = (generated.get("corrected_text") or "").strip() or normalized
                safe_text = (
                    candidate
                    if semantic_tokens(candidate) == semantic_tokens(normalized)
                    else normalized
                )

                record = {
                    "id": source["id"],
                    "start": source.get("start"),
                    "end": source.get("end"),
                    "synthetic": bool(source.get("synthetic")),
                    "raw_text": raw_text,
                    "safe_text": safe_text,
                    "suggested_text": candidate,
                    "paragraph_break_after": bool(
                        generated.get("paragraph_break_after")
                    ),
                    "section_title": clean_section_title(
                        generated.get("section_title") or ""
                    ),
                    "commands": validated_commands(
                        safe_text, generated.get("commands") or []
                    ),
                }

                if safe_text != raw_text:
                    proposal_counter += 1
                    proposals.append(
                        {
                            "id": f"proposal-{proposal_counter:06d}",
                            "segment_id": source["id"],
                            "kind": "validated_correction",
                            "original": raw_text,
                            "proposed": safe_text,
                            "selected_by_default": True,
                            "validated": True,
                            "dangerous": contains_dangerous_command(safe_text),
                            "reason": "Pontuação/caixa ou regra contextual conhecida.",
                        }
                    )

                if semantic_tokens(candidate) != semantic_tokens(normalized):
                    proposal_counter += 1
                    proposals.append(
                        {
                            "id": f"proposal-{proposal_counter:06d}",
                            "segment_id": source["id"],
                            "kind": "lexical_suggestion",
                            "original": safe_text,
                            "proposed": candidate,
                            "selected_by_default": False,
                            "validated": False,
                            "dangerous": contains_dangerous_command(candidate),
                            "reason": (
                                "Mudança lexical não comprovada; exige decisão humana."
                            ),
                        }
                    )

                if generated.get("remove_as_outtake"):
                    proposal_counter += 1
                    proposals.append(
                        {
                            "id": f"proposal-{proposal_counter:06d}",
                            "segment_id": source["id"],
                            "kind": "outtake",
                            "original": raw_text,
                            "proposed": "",
                            "selected_by_default": True,
                            "validated": False,
                            "dangerous": False,
                            "reason": (
                                generated.get("outtake_reason")
                                or "Segmento indicado como outtake pelo modelo."
                            ),
                        }
                    )
                records.append(record)

        bundle = {
            "version": 1,
            "segments": records,
            "proposals": proposals,
        }
        compiled = compile_revision(bundle)
        elapsed = time.perf_counter() - started
        usage = aggregate_usage(usage_rows)
        usage["elapsed_seconds"] = round(elapsed, 3)

        if progress_callback:
            progress_callback(
                {
                    "stage": "transcript_improvement",
                    "chunk": len(chunks),
                    "chunks": len(chunks),
                    "percent": 100,
                }
            )

        return {
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
            "glossary_version": GLOSSARY_VERSION,
            "source_text_sha256": sha256_text(source_text),
            "source_segments_sha256": sha256_segments(source_segments),
            "improved_text": compiled["improved_text"],
            "improved_segments": compiled["improved_segments"],
            "study_markdown": compiled["study_markdown"],
            "proposals": bundle,
            "decisions": compiled["decisions"],
            "outtakes": compiled["outtakes"],
            "chunk_count": len(chunks),
            "usage": usage,
        }

    def persist_draft(self, transcription_id: int, result: Dict[str, Any]):
        from database import create_transcription_revision

        return create_transcription_revision(
            transcription_id,
            model=result["model"],
            prompt_version=result["prompt_version"],
            glossary_version=result["glossary_version"],
            improved_text=result["improved_text"],
            improved_segments=result["improved_segments"],
            study_markdown=result["study_markdown"],
            proposals=result["proposals"],
            decisions=result["decisions"],
            outtakes=result["outtakes"],
            chunk_count=result["chunk_count"],
            usage=result["usage"],
        )

    @staticmethod
    def normalize_segments(
        full_text: str,
        segments: Sequence[Dict[str, Any]] | None,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if segments:
            for index, segment in enumerate(segments, 1):
                text = str(segment.get("text") or "").strip()
                if not text:
                    continue
                normalized.append(
                    {
                        "id": f"seg-{index:06d}",
                        "start": float(segment.get("start") or 0),
                        "end": float(segment.get("end") or 0),
                        "text": text,
                        "synthetic": False,
                    }
                )
            return normalized

        sentences = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+|\n+", full_text or "")
            if part.strip()
        ]
        for index, text in enumerate(sentences, 1):
            normalized.append(
                {
                    "id": f"text-{index:06d}",
                    "start": None,
                    "end": None,
                    "text": text,
                    "synthetic": True,
                }
            )
        return normalized

    def build_chunks(self, segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        start = 0
        while start < len(segments):
            end = start
            char_count = 0
            while end < len(segments):
                next_size = len(segments[end]["text"]) + 1
                if end > start and char_count + next_size > self.chunk_chars:
                    break
                char_count += next_size
                end += 1
            central = list(segments[start:end])
            context = []
            if start > 0:
                context.append(dict(segments[start - 1]))
            if end < len(segments):
                context.append(dict(segments[end]))
            chunks.append({"central": central, "context": context})
            start = end
        return chunks

    def _run_chunk_with_retry(
        self,
        transcription: Dict[str, Any],
        chunk: Dict[str, Any],
        cancel_check: Callable[[], bool],
    ) -> Dict[str, Any]:
        expected_ids = [item["id"] for item in chunk["central"]]
        last_error: Exception | None = None
        for attempt in (1, 2):
            if cancel_check():
                raise TranscriptImprovementCancelled("Aprimoramento cancelado")
            try:
                response = self.client.chat_json(
                    self._messages_for(transcription, chunk, attempt),
                    CHUNK_RESPONSE_SCHEMA,
                    options={
                        "temperature": 0,
                        "seed": 42,
                        "num_ctx": self.num_ctx,
                    },
                    timeout=self.timeout,
                    keep_alive="10m",
                )
                actual_ids = [
                    item.get("id") for item in response["data"].get("segments", [])
                ]
                if actual_ids != expected_ids:
                    raise TranscriptImprovementError(
                        "Resposta não cobriu exatamente os segmentos centrais"
                    )
                return response
            except TranscriptImprovementCancelled:
                raise
            except Exception as exc:
                last_error = exc
        raise TranscriptImprovementError(
            f"Chunk inválido após duas tentativas: {last_error}"
        ) from last_error

    @staticmethod
    def _messages_for(
        transcription: Dict[str, Any],
        chunk: Dict[str, Any],
        attempt: int,
    ) -> List[Dict[str, str]]:
        payload = []
        central_ids = {item["id"] for item in chunk["central"]}
        merged = sorted(
            chunk["context"] + chunk["central"],
            key=lambda item: item["id"],
        )
        for item in merged:
            payload.append(
                {
                    "id": item["id"],
                    "text": item["text"],
                    "context_only": item["id"] not in central_ids,
                }
            )
        retry_note = (
            "\nEsta é uma repetição: copie os IDs centrais exatamente e não devolva contexto."
            if attempt == 2
            else ""
        )
        user = {
            "video": {
                "title": transcription.get("video_title") or "",
                "channel": transcription.get("channel") or "",
                "language": transcription.get("language") or "pt",
            },
            "segments": payload,
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT + retry_note},
            {
                "role": "user",
                "content": json.dumps(user, ensure_ascii=False, sort_keys=True),
            },
        ]


def compile_revision(
    bundle: Dict[str, Any],
    selected_ids: Iterable[str] | None = None,
) -> Dict[str, Any]:
    proposals = list(bundle.get("proposals") or [])
    if selected_ids is None:
        selected = {
            item["id"] for item in proposals if item.get("selected_by_default")
        }
    else:
        selected = set(selected_ids)
    proposals_by_segment: Dict[str, List[Dict[str, Any]]] = {}
    for proposal in proposals:
        proposals_by_segment.setdefault(proposal["segment_id"], []).append(proposal)

    faithful_segments: List[Dict[str, Any]] = []
    paragraphs: List[str] = []
    paragraph: List[str] = []
    markdown: List[str] = []
    markdown_paragraph: List[str] = []
    outtakes: List[Dict[str, Any]] = []
    last_heading = ""
    has_real_timestamps = any(
        not item.get("synthetic") for item in bundle.get("segments") or []
    )

    def flush_paragraph():
        if paragraph:
            paragraphs.append(" ".join(paragraph).strip())
            paragraph.clear()

    def flush_markdown():
        if markdown_paragraph:
            markdown.append(" ".join(markdown_paragraph).strip())
            markdown.append("")
            markdown_paragraph.clear()

    for record in bundle.get("segments") or []:
        text = record.get("raw_text") or ""
        remove = None
        for proposal in proposals_by_segment.get(record["id"], []):
            if proposal["id"] not in selected:
                continue
            if proposal["kind"] == "validated_correction":
                text = proposal.get("proposed") or text
            elif proposal["kind"] == "lexical_suggestion":
                text = proposal.get("proposed") or text
            elif proposal["kind"] == "outtake":
                remove = proposal
        if remove is not None:
            outtakes.append(
                {
                    "segment_id": record["id"],
                    "text": record.get("raw_text") or "",
                    "reason": remove.get("reason") or "",
                }
            )
            continue

        if not record.get("synthetic"):
            faithful_segments.append(
                {
                    "start": record.get("start") or 0,
                    "end": record.get("end") or 0,
                    "text": text,
                }
            )
        paragraph.append(text)

        heading = clean_section_title(record.get("section_title") or "")
        if heading and heading != last_heading:
            flush_markdown()
            markdown.append(f"## {heading}")
            markdown.append("")
            last_heading = heading

        commands = [
            command
            for command in record.get("commands") or []
            if command.get("text") and command["text"] in text
        ]
        if commands and text.strip() in {item["text"].strip() for item in commands}:
            flush_markdown()
            markdown.extend(["```bash", text.strip(), "```", ""])
        else:
            rendered = text
            for command in commands:
                rendered = rendered.replace(
                    command["text"], f"`{command['text']}`"
                )
            markdown_paragraph.append(rendered)

        if record.get("paragraph_break_after"):
            flush_paragraph()
            flush_markdown()

    flush_paragraph()
    flush_markdown()
    improved_text = "\n\n".join(item for item in paragraphs if item).strip()
    study_markdown = "\n".join(markdown).strip()
    if study_markdown and not study_markdown.startswith("# "):
        study_markdown = "# Transcrição aprimorada\n\n" + study_markdown

    return {
        "improved_text": improved_text,
        "improved_segments": faithful_segments if has_real_timestamps else None,
        "study_markdown": study_markdown,
        "outtakes": outtakes,
        "decisions": {"selected_proposal_ids": sorted(selected)},
    }


def normalize_known_terms(text: str, *, context: str = "") -> str:
    result = text or ""
    result = re.sub(r"\b(?:calcei|calc[eê]|calcey)\b", "cowsay", result, flags=re.I)
    result = re.sub(
        r"\bdigital\s+(?:ouxa|ouça|ocean)\b",
        "DigitalOcean",
        result,
        flags=re.I,
    )
    result = re.sub(r"\bnode\s+jts\b", "Node.js", result, flags=re.I)
    result = re.sub(
        r"\b(?:coppe|cop)\s+peixe\b",
        "copy-paste",
        result,
        flags=re.I,
    )
    result = re.sub(
        r"\blocal\s*(?:rosto|roche|host)\s*[: ]?\s*(\d{2,5})\b",
        lambda match: f"localhost:{match.group(1)}",
        result,
        flags=re.I,
    )
    result = re.sub(
        r"\bsudu\s+rm\s+(?:tra[cç]o\s+)?rf\s+barra\b",
        "sudo rm -rf /",
        result,
        flags=re.I,
    )
    result = re.sub(
        r"\brm\s+tra[cç]o\s+rf\s+barra\b",
        "rm -rf /",
        result,
        flags=re.I,
    )
    result = re.sub(
        r"\bbairro\s+(?:itc|etc)\s+ssh\s+sshd?\s+(?:de\s+)?config\b",
        "/etc/ssh/sshd_config",
        result,
        flags=re.I,
    )

    lowered_context = f"{context} {text}".casefold()
    if any(token in lowered_context for token in ("javascript", "node", "runtime", "npm")):
        result = re.sub(r"\bnude\b", "Node.js", result, flags=re.I)
    if any(token in lowered_context for token in ("ssh", "processo", "serviço", "service")):
        result = re.sub(
            r"\b(?:dimos|de mão|demo)\b",
            "daemon",
            result,
            flags=re.I,
        )
    return result


def semantic_tokens(text: str) -> List[str]:
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return re.findall(r"[\wÀ-ÿ]+", normalized, flags=re.UNICODE)


def clean_section_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value or "").strip().strip("#").strip()
    if len(title) > 100:
        title = title[:100].rstrip()
    return title


def contains_dangerous_command(text: str) -> bool:
    return bool(
        re.search(
            r"(?:^|\s)(?:sudo\s+)?rm\s+-rf\s+/(?:\s|$|[,.!?;:])",
            text or "",
            re.I,
        )
    )


def validated_commands(
    safe_text: str,
    model_commands: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = []
    seen = set()
    known = []
    known.extend(
        match.group(0).strip()
        for match in re.finditer(
            r"(?:sudo\s+)?rm\s+-rf\s+/(?=\s|$|[,.!?;:])",
            safe_text or "",
            re.I,
        )
    )
    known.extend(
        match.group(0).strip()
        for match in re.finditer(
            r"\bssh\s+(?:-[A-Za-z](?:\s+\S+)?\s*)+\S*",
            safe_text or "",
        )
    )
    for command in list(model_commands) + [
        {"text": item, "dangerous": contains_dangerous_command(item)}
        for item in known
    ]:
        value = str(command.get("text") or "").strip()
        if not value or value not in safe_text or value in seen:
            continue
        seen.add(value)
        commands.append(
            {
                "text": value,
                "dangerous": bool(
                    command.get("dangerous") or contains_dangerous_command(value)
                ),
            }
        )
    return commands


def aggregate_usage(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, Any] = {"requests": len(rows)}
    for key in (
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "prompt_eval_duration",
        "eval_count",
        "eval_duration",
    ):
        values = [row.get(key) for row in rows if isinstance(row.get(key), (int, float))]
        if values:
            totals[key] = sum(values)
    return totals


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_segments(segments: Any) -> str | None:
    if segments is None:
        return None
    payload = json.dumps(
        segments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
