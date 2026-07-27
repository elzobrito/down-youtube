#!/usr/bin/env bash
# Smoke test: health + stats + query on YouTube LTM RAG base.
set -euo pipefail

DB="${RAG_SQLITE_DB:-${HOME}/.youtube_transcriber/youtube_rag.sqlite}"
CLI="${RAG_SQLITE_CLI:-rag-sqlite}"
QUERY="${1:-Behemoth monstro bíblico}"

if ! command -v "$CLI" >/dev/null 2>&1; then
  if [[ -x "${HOME}/.local/bin/rag-sqlite" ]]; then
    CLI="${HOME}/.local/bin/rag-sqlite"
  elif [[ -f "${HOME}/desenvolvimento/rag-sqlite/rag_sqlite.py" ]]; then
    CLI=(python3 "${HOME}/desenvolvimento/rag-sqlite/rag_sqlite.py")
  else
    echo "rag-sqlite CLI not found" >&2
    exit 2
  fi
else
  CLI=("$CLI")
fi

if [[ ! -f "$DB" ]]; then
  echo "RAG DB missing: $DB" >&2
  echo "Run backfill from the app (Settings → Memória) or:" >&2
  echo "  python3 -c \"from core.rag_bridge import backfill_all_transcriptions; print(backfill_all_transcriptions())\"" >&2
  exit 3
fi

echo "== health =="
"${CLI[@]}" --db "$DB" --compact health
echo "== stats =="
"${CLI[@]}" --db "$DB" --compact stats
echo "== query: $QUERY =="
"${CLI[@]}" --db "$DB" --compact query "$QUERY" --top-k 5 --min-score 0.05

MANIFEST="${DB%/*}/rag_manifest.jsonl"
if [[ -f "$MANIFEST" ]]; then
  echo "== manifest lines =="
  wc -l < "$MANIFEST"
fi

echo "OK: memory smoke finished"
