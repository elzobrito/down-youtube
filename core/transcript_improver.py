"""Conservative, auditable post-ASR improvement with local Ollama models."""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Sequence

from core.ollama_client import OllamaClient


PROMPT_VERSION = "transcript-improve-v2"
GLOSSARY_VERSION = "technical-pt-v1"
DEFAULT_MODEL = "phi4-mini:latest"
# Smaller chunks improve JSON adherence on phi4-mini for long ASR.
DEFAULT_CHUNK_CHARS = 2800
DEFAULT_MAX_SEGMENTS_PER_CHUNK = 18
DEFAULT_NUM_CTX = 12288


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
Devolva um objeto JSON com a chave "segments" e um item por ID central.
""".strip()


class TranscriptImprover:
    def __init__(
        self,
        *,
        client: OllamaClient | None = None,
        model: str = DEFAULT_MODEL,
        chunk_chars: int = DEFAULT_CHUNK_CHARS,
        max_segments_per_chunk: int = DEFAULT_MAX_SEGMENTS_PER_CHUNK,
        timeout: float = 180,
        num_ctx: int = DEFAULT_NUM_CTX,
    ):
        self.model = model or DEFAULT_MODEL
        self.client = client or OllamaClient(model=self.model)
        self.chunk_chars = max(500, int(chunk_chars))
        self.max_segments_per_chunk = max(1, int(max_segments_per_chunk))
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
                segment_count = end - start
                if end > start and (
                    char_count + next_size > self.chunk_chars
                    or segment_count >= self.max_segments_per_chunk
                ):
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

    @staticmethod
    def align_chunk_segments(
        central: Sequence[Dict[str, Any]],
        raw_segments: Sequence[Dict[str, Any]] | None,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Map model output onto expected central IDs.

        - Keep first occurrence of each known id
        - Drop extras (context_only / unknown)
        - Fill missing ids with the original segment text (safe fallback)
        - Always return segments in the original central order
        """
        by_id: Dict[str, Dict[str, Any]] = {}
        for item in raw_segments or []:
            if not isinstance(item, dict):
                continue
            sid = item.get("id")
            if not sid or sid in by_id:
                continue
            by_id[str(sid)] = item

        expected_ids = [str(item["id"]) for item in central]
        expected_set = set(expected_ids)
        aligned: List[Dict[str, Any]] = []
        missing: List[str] = []
        for source in central:
            sid = str(source["id"])
            generated = by_id.get(sid)
            if generated is None:
                missing.append(sid)
                aligned.append(
                    {
                        "id": sid,
                        "corrected_text": source["text"],
                        "paragraph_break_after": False,
                        "remove_as_outtake": False,
                        "outtake_reason": "",
                        "section_title": "",
                        "commands": [],
                        "_filled_from_original": True,
                    }
                )
                continue
            row = dict(generated)
            row["id"] = sid
            if not str(row.get("corrected_text") or "").strip():
                row["corrected_text"] = source["text"]
                row["_filled_from_original"] = True
            row.setdefault("paragraph_break_after", False)
            row.setdefault("remove_as_outtake", False)
            row.setdefault("outtake_reason", "")
            row.setdefault("section_title", "")
            row.setdefault("commands", [])
            aligned.append(row)

        extra = [sid for sid in by_id if sid not in expected_set]
        matched = len(expected_ids) - len(missing)
        stats = {
            "expected": len(expected_ids),
            "matched": matched,
            "missing_ids": missing,
            "extra_ids": extra,
            "coverage": (matched / len(expected_ids)) if expected_ids else 1.0,
        }
        return aligned, stats

    def _run_chunk_with_retry(
        self,
        transcription: Dict[str, Any],
        chunk: Dict[str, Any],
        cancel_check: Callable[[], bool],
    ) -> Dict[str, Any]:
        expected_ids = [item["id"] for item in chunk["central"]]
        last_error: Exception | None = None
        best_aligned: List[Dict[str, Any]] | None = None
        best_stats: Dict[str, Any] | None = None
        best_usage: Dict[str, Any] = {}

        for attempt in (1, 2):
            if cancel_check():
                raise TranscriptImprovementCancelled("Aprimoramento cancelado")
            try:
                response = self.client.chat_json(
                    self._messages_for(
                        transcription,
                        chunk,
                        attempt,
                        expected_count=len(expected_ids),
                    ),
                    CHUNK_RESPONSE_SCHEMA,
                    options={
                        "temperature": 0,
                        "seed": 42,
                        "num_ctx": self.num_ctx,
                    },
                    timeout=self.timeout,
                    keep_alive="10m",
                )
                raw = (response.get("data") or {}).get("segments") or []
                aligned, stats = self.align_chunk_segments(chunk["central"], raw)
                usage = response.get("usage") or {}

                if best_stats is None or stats["coverage"] > best_stats["coverage"]:
                    best_aligned = aligned
                    best_stats = stats
                    best_usage = usage

                # Perfect coverage: done
                if stats["coverage"] >= 1.0 and not stats["missing_ids"]:
                    return {
                        "data": {"segments": aligned, "alignment": stats},
                        "usage": usage,
                    }

                # Partial coverage is usable; retry once only when nothing matched
                if stats["matched"] > 0:
                    return {
                        "data": {"segments": aligned, "alignment": stats},
                        "usage": usage,
                    }

                last_error = TranscriptImprovementError(
                    self._format_coverage_error(expected_ids, raw, stats)
                )
            except TranscriptImprovementCancelled:
                raise
            except Exception as exc:
                last_error = exc

        # After retries: prefer best partial alignment; else fill entire chunk
        # from original text so long episodes still complete.
        if best_aligned is not None and best_stats is not None:
            return {
                "data": {
                    "segments": best_aligned,
                    "alignment": {**best_stats, "fallback": "partial_or_original"},
                },
                "usage": best_usage,
            }

        filled, stats = self.align_chunk_segments(chunk["central"], [])
        return {
            "data": {
                "segments": filled,
                "alignment": {
                    **stats,
                    "fallback": "original_after_errors",
                    "last_error": str(last_error) if last_error else None,
                },
            },
            "usage": {},
        }

    @staticmethod
    def _format_coverage_error(
        expected_ids: Sequence[str],
        raw_segments: Sequence[Dict[str, Any]],
        stats: Dict[str, Any],
    ) -> str:
        actual = [item.get("id") for item in (raw_segments or []) if isinstance(item, dict)]
        missing = stats.get("missing_ids") or []
        extra = stats.get("extra_ids") or []
        miss_s = list(missing[:8]) + (["…"] if len(missing) > 8 else [])
        extra_s = list(extra[:8]) + (["…"] if len(extra) > 8 else [])
        return (
            "Resposta não cobriu os segmentos centrais: "
            f"esperados={len(expected_ids)}, recebidos={len(actual)}, "
            f"casados={stats.get('matched', 0)}, "
            f"faltando={miss_s}, extras={extra_s}"
        )

    @staticmethod
    def _messages_for(
        transcription: Dict[str, Any],
        chunk: Dict[str, Any],
        attempt: int,
        *,
        expected_count: int | None = None,
    ) -> List[Dict[str, str]]:
        payload = []
        central_ids = {item["id"] for item in chunk["central"]}
        # Preserve timeline order (start index), not lexical id sort alone —
        # ids are zero-padded so sort works, but explicit order is safer.
        merged = list(chunk["context"] + chunk["central"])
        merged.sort(key=lambda item: item["id"])
        for item in merged:
            payload.append(
                {
                    "id": item["id"],
                    "text": item["text"],
                    "context_only": item["id"] not in central_ids,
                }
            )
        count = expected_count if expected_count is not None else len(central_ids)
        retry_note = ""
        if attempt == 2:
            retry_note = (
                "\nEsta é uma repetição: devolva EXATAMENTE os "
                f"{count} IDs centrais (context_only=false), na mesma ordem, "
                "sem IDs de contexto e sem omitir nenhum."
            )
        user = {
            "video": {
                "title": transcription.get("video_title") or "",
                "channel": transcription.get("channel") or "",
                "language": transcription.get("language") or "pt",
            },
            "central_id_count": count,
            "central_ids": [item["id"] for item in chunk["central"]],
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
