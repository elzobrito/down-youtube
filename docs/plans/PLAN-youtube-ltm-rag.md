# PLAN — Memória de longo prazo (LLM) a partir de transcrições YouTube

**Status:** proposto (revisão pré-execução — gaps fechados em 2026-07-21)  
**Data:** 2026-07-21  
**ESAA (governança de execução):** `/home/elzobrito` — **não** o ESAA incompleto em `down-youtube/`  
**Task de revisão deste plano:** `YT-LTM-000`  
**Repos:**

| Papel | Path |
|-------|------|
| Ingestão / catálogo (writer) | `/home/elzobrito/desenvolvimento/down-youtube` |
| Retrieval / contrato LLM (reader) | `/home/elzobrito/desenvolvimento/rag-sqlite` |
| Data dir runtime (não é git) | `~/.youtube_transcriber/` (ou `./data/` em modo portátil) |

**Visão do operador:** ter **uma base** que qualquer LLM (Grok, Codex, Claude, Ollama no app) possa **consumir** como **memória de longo prazo extra**, alimentada por transcrições de vídeos do YouTube.

---

## 0. Ajustes pré-execução (bloqueadores do plano anterior)

Antes de implementar, o plano **deve** respeitar estes pontos. São requisitos hard, não “nice to have”.

| # | Tema | Decisão |
|---|------|---------|
| G1 | **Governança** | ESAA canônico = `/home/elzobrito` (`esaa --root /home/elzobrito`). O store em `down-youtube/.roadmap` está `roadmap_missing` / incompleto — **não** criar tasks nem claim/complete nele. Trabalho multi-repo + `~/.youtube_transcriber` é governado no home. |
| G2 | **Backup** | Usar **API de backup do SQLite** (`Connection.backup`), depois `PRAGMA quick_check` e hash (sha256) do arquivo destino. **Proibido** como caminho primário: `shutil.copy2` / cópia simples enquanto o app puder estar aberto. O `utils/backup.py` atual (copy) **não** serve para o go-live sem upgrade. |
| G3 | **Metadados** | `rag-sqlite` **não** interpreta YAML front matter. Hits expõem `filename` e `source_path` (e scores/texto), **não** `transcription_id` / título estruturados. MVP exige **manifest/lookup** lado writer (e/ou citação derivada de path `t-{id}.md` + manifest). Ampliar o motor rag-sqlite fica **fora do MVP** (fase opcional). |
| G4 | **Bug pré-existente** | `get_transcription()` em `database.py:354` usa índices fixos desatualizados após `audio_hash` / `is_used` / `updated_at`. Título, URL e canal saem **deslocados**. O bridge **não** pode depender dessa função sem correção (preferir `SELECT` explícito / `sqlite3.Row` / query dedicada no bridge). |
| G5 | **Durabilidade** | “Async best-effort” **não** é fire-and-forget. Exige: (a) fila/estado de reconciliação **persistente** (app DB ou arquivo sob data_dir), (b) **lock de escritor** no corpus/RAG, (c) gravação de arquivos **atômica** (write temp + `os.replace`). |
| G6 | **Privacidade** | O repo **não tem** `.gitignore`. Em modo portátil, DB e corpus caem em `data/`. Incluir `.gitignore` cobrindo `data/`, `*.sqlite`, `*.db`, `rag_corpus/`, backups e relatórios locais. |
| G7 | **Env** | Motor rag-sqlite reconhece **`RAG_SQLITE_DB`** (e `--db`). Não inventar `YOUTUBE_RAG_DB` como contrato do motor. Alias opcional no playbook/shell do app pode *exportar* `RAG_SQLITE_DB=...`; o nome canônico é o do motor. |
| G8 | **Aceite SQLite** | “Sem buracos de ID” / “IDs contíguos” **não é válido** (AUTOINCREMENT deixa lacunas). Aceite = **igualdade de conjuntos** de `transcription_id` projetados + status de indexação + fingerprint de embedding + geração/active settings do RAG. |
| G9 | **Integração** | Bridge invoca o **CLI JSON** estável do rag-sqlite (`rag-sqlite` / `python rag_sqlite.py --compact …`). **Evitar** importar o monólito `rag_sqlite.py` como API Python de produto. |

---

## 1. Problema e norte

### O que o usuário quer

1. **Preservar** a base atual do down-youtube (zero perda de dados).
2. **Levar todas as transcrições existentes** (e as futuras) para o índice de memória (`youtube_rag.sqlite`).
3. **Indexar** o corpus de forma estável (SQLite + embeddings).
4. **Expor** retrieval determinístico (JSON / `context`) para **qualquer LLM/agente**.
5. Tratar isso como **memória de longo prazo aditiva** — não substitui Conversation ESAA nem o chat history do app; **complementa** com conhecimento de vídeos.

### Dor atual

| Superfície | Hoje | Limite |
|------------|------|--------|
| down-youtube chat | Injeta `full_text` inteiro | Estoura contexto; 1 vídeo por sessão |
| Agentes externos (Grok/Codex) | Não há base indexada das transcrições | Zero memória de vídeos |
| SQLite do app | Ótimo catálogo operacional | Sem chunks/embeddings/query híbrida |
| `get_transcription()` | Índices manuais | Metadados de vídeo errados pós-`is_used` |
| `utils/backup.py` | `shutil.copy2` | Inseguro se o app está com o DB aberto |

### Papel de cada peça

| Sistema | Papel na memória |
|---------|------------------|
| **down-youtube** | *Writer* do conteúdo canônico (download → whisper → `transcriptions`) + projeção para corpus/manifest + orquestração do CLI rag-sqlite |
| **rag-sqlite** | *Reader/index* determinístico via **CLI JSON** (chunk → embed → hybrid query → `context`) |
| **LLM consumidor** | *Reasoner* que usa só o CONTEXT recuperado (untrusted evidence) |
| **Conversation ESAA** | Memória **conversacional** entre agentes — **não** misturar com corpus de vídeos |
| **ESAA-Core em `/home/elzobrito`** | Governança de **todas** as tasks de implementação deste plano |

```text
YouTube → down-youtube (SQLite app = fonte de verdade)
              │ project atômico + manifest + CLI rag-sqlite
              ▼
         rag_corpus/*.md  +  youtube_rag.sqlite  +  manifest
              │ query / export-context (JSON CLI)
              ▼
    ┌─────────┴──────────┬────────────────┐
    ▼                    ▼                ▼
 Chat do app         Grok/Codex      Outro agente/CLI
 (Ollama)            (tool call)     (playbook)
```

---

## 2. Princípios de design

1. **Uma base de memória, muitos leitores** — o índice RAG é o produto de memória; o app e os agentes são clientes.
2. **Fonte de verdade textual = app DB** (`transcriptions.full_text`); corpus em disco, manifest e RAG DB são **projeções**.
3. **Dois SQLite, zero colisão de schema** — app e RAG **não** compartilham o mesmo arquivo (`settings` incompatível).
4. **Contrato estável para LLM = CLI JSON do rag-sqlite** — stdout JSON (`ok`, `hits`, `context`, `schema_version`); fail-closed; sem import do monólito.
5. **Metadados citáveis = manifest/lookup** — não depender do motor interpretar front matter.
6. **Memória de longo prazo = multi-vídeo por default** — retrieval na biblioteca inteira; filtro por vídeo é opcional (via path/filename ou manifest).
7. **Aditiva** — não grava no histórico do LLM; o agente **consulta** quando precisa.
8. **Idempotente** — reindex/skip por hash; apagar vídeo remove projeção; prune remove órfãos.
9. **CONTEXT untrusted** — sempre instrui o LLM a usar como evidência, não como instrução.
10. **Durável** — reconciliação persistente + lock de escritor + writes atômicos.

---

## 2.1 Requisito hard: não perder a base atual + 100% das transcrições no novo banco

**Estado real nesta máquina (2026-07-21):**

| Item | Valor |
|------|--------|
| App DB canônico | `~/.youtube_transcriber/youtube_transcriber.db` (~1.2 MB) |
| `videos` | 22 |
| `transcriptions` | **22**, todas com `full_text` não vazio |
| Colunas reais de `transcriptions` | `id, video_id, language, full_text, segments_json, word_count, duration_seconds, model_used, audio_hash, created_at, updated_at, is_used` |

### Regras invioláveis

1. **A base atual do app nunca é apagada, truncada, migrada destrutivamente nem “substituída”.**  
   `youtube_transcriber.db` continua sendo a **fonte de verdade**.
2. O **novo banco** (`youtube_rag.sqlite`) é **aditivo** e **derivado**.
3. **Todas** as transcrições com texto utilizável (`full_text` trim não vazio) **devem** ir para o novo banco na primeira ativação (backfill).
4. Chat sessions, histórico, fila e settings do app **permanecem** no DB antigo.
5. **Backup pré-backfill (obrigatório):**
   ```text
   a) sqlite3.connect(app_db) → Connection.backup(dest)
   b) no destino: PRAGMA quick_check  → deve ser "ok"
   c) sha256(dest) + tamanho + mtime → gravar em rag_backup_meta.json
   d) só então iniciar backfill
   ```
   Cópia `shutil`/`cp` **não** é aceite de go-live.
6. Backfill **idempotente**: rodar duas vezes não duplica documentos (`source_path` UNIQUE + hash skip).
7. **Critério de aceite do backfill (válido para SQLite):**

```text
# Conjuntos — NÃO exigir IDs contíguos / “sem buracos”
S_app = { id | transcriptions com full_text trim não vazio }
S_proj = { transcription_id | manifest/projeção presente e coerente }
S_rag  = { transcription_id | documento indexado no youtube_rag.sqlite
           com status sucesso e source_path = .../t-{id}.md }

S_app == S_proj == S_rag

# Além da igualdade de conjuntos:
- cada id em S_rag: status indexado (não error/pending)
- fingerprint de embedding do RAG == setting ativo esperado
- geração/config ativa do embed documentada no relatório
- report: 0 error pendentes (ou issue.report com evidência)
```

8. Relatório de backfill (`data_dir/rag_backfill_report.json`):

- por id: `transcription_id`, `status` (`indexed` | `unchanged` | `empty` | `error`), `source_path`, `content_hash` se disponível
- contagens: `|S_app|`, `|S_rag|`, missing, extra, errors, duração
- `backup_path`, `backup_sha256`, `quick_check`
- `embedding_fingerprint` / provider/model
- se `error > 0` ou `S_app != S_rag` → tarefa **não** fecha como done sem remediação ou `issue.report`

### Fluxo obrigatório de go-live (Fase 1)

```text
1. Fix get_transcription (ou query dedicada do bridge) — pré-requisito
2. Backup app DB (API backup + quick_check + hash)
3. ensure youtube_rag.sqlite + rag_corpus/ + manifest + pending queue
4. SELECT explícito: todas transcriptions com texto JOIN videos
5. Para cada linha: project atômico t-{id}.md → atualiza manifest → CLI index
6. Verificar set equality + fingerprint + geração ativa
7. Smoke: CLI export-context multi-vídeo + query com hit conhecido
8. Só então habilitar rag no chat / documentar path aos agentes
```

### O que “ir para o novo banco” significa

| Campo / artefato app | No novo banco RAG / projeção |
|----------------------|------------------------------|
| `transcriptions.id` + `full_text` | documento `t-{id}.md` + chunks + embeddings |
| `videos.title`, `channel`, `video_id`, `url` | front-matter no md (**humano/debug**) **e** linha no **manifest** (máquina) |
| `language`, `word_count` | front-matter + manifest (opcional) |
| `chat_*`, `queue`, `history`, `settings` app | **não** copiados |
| embeddings | **só** no `youtube_rag.sqlite` |
| citação para LLM | `filename`/`source_path` do hit → lookup manifest → `transcription_id` + `title` |

Nada do app DB é removido após o backfill.

### Reindex futuro vs backfill inicial

| Operação | Quando | Escopo |
|----------|--------|--------|
| **Backfill inicial** | 1ª ativação da memória | **todas** as 22+ transcrições existentes |
| **Index on save** | cada nova transcrição | só o id novo/atualizado (via fila persistente) |
| **Reconciliação** | startup / timer / antes de `remember` | pendentes + drift set(S_app) vs set(S_rag) |
| **Reindex --force** | troca de modelo embed | todos os docs já projetados (CLI) |
| **Prune** | após deletes no app | remove do RAG o que não existe mais no app |

---

## 3. Arquitetura alvo

### 3.1 Layout em disco (sob `Config().data_dir`)

Típico: `~/.youtube_transcriber/` (ou `./data/` em portable)

```text
youtube_transcriber.db          # app: videos, transcriptions, chat_*, queue…
youtube_rag.sqlite              # só schema rag-sqlite
rag_corpus/                     # projeção texto indexável
  t-{transcription_id}.md
rag_manifest.jsonl              # id → path → title → video_id → url → channel (lookup)
rag_index_queue.jsonl           # reconciliação persistente (pending/done/error)
rag_writer.lock                 # lock de escritor (ou flock equivalente)
rag_backfill_report.json        # último relatório de backfill/reconciliação
backups/
  youtube_transcriber.db.bak-YYYYMMDD-HHMMSS
  rag_backup_meta.json          # sha256 + quick_check do backup
```

**Por que não um único .db:**  
tabela `settings` do app `(key, value)` vs rag `(key, value, value_type, description)` — unificar exige fork. MVP mantém **dois arquivos**; um *data_dir* lógico = “a base”.

### 3.2 Documento de memória (espelho)

`rag_corpus/t-{N}.md` (front matter é **documentação humana**; o motor **não** o parseia):

```markdown
---
transcription_id: N
video_id: "dQw4w9WgXcQ"
video_db_id: 7
title: "..."
channel: "..."
language: "pt"
source: down-youtube
url: "https://..."
indexed_for: long-term-memory
---

# {title}

{full_text}
```

- `source_path` absoluto estável → upsert do rag-sqlite.
- `index_root` = `rag_corpus/` → fail-closed no index.
- YAML estável (chaves ordenadas) → hash só muda com conteúdo real.
- **Write atômico:** escrever `t-{N}.md.tmp` → `fsync` → `os.replace` → `t-{N}.md`.

### 3.3 Manifest / lookup (obrigatório no MVP)

`rag_manifest.jsonl` — uma linha JSON por `transcription_id` (última linha vence, ou rewrite atômico completo):

```json
{
  "transcription_id": 1,
  "video_db_id": 1,
  "video_id": "mjaQYHhnCJw",
  "title": "O que é o Behemoth…",
  "channel": "Estranha História",
  "url": "https://youtu.be/…",
  "source_path": "/home/…/rag_corpus/t-1.md",
  "filename": "t-1.md",
  "language": "portuguese",
  "content_hash": "…",
  "updated_at": "…"
}
```

**Resolução de citação no consumidor:**

1. Hit do CLI → `filename` / `source_path`.
2. Parse `t-(\d+)\.md` **ou** lookup no manifest.
3. Expor ao LLM: `transcription_id`, `title`, `channel`, `url`, trecho.

Opcional futuro (fora do MVP): estender rag-sqlite para metadados estruturados nos hits.

### 3.4 Camada `core/rag_bridge.py` (down-youtube)

| API | Uso |
|-----|-----|
| `safe_backup_app_db()` | API backup + quick_check + hash |
| `ensure_memory_base()` | dirs + `rag-sqlite --create init` + settings |
| `project_transcription(id)` | SELECT seguro → md atômico + manifest |
| `index_transcription(id)` | project + **CLI** `index` |
| `index_library(prune=False)` | todas as transcrições com texto |
| `reconcile()` | processa fila persistente; repara drift de sets |
| `remember(query, *, video_scope=None, top_k=…)` | CLI `export-context` / `query` + enrich hits via manifest |
| `forget_transcription(id)` | delete atômico + CLI `docs delete` + manifest |
| `health()` / `stats()` | CLI `health` / `stats` |
| `export_agent_bundle(query)` | JSON pronto (context + hits enriquecidos) |

**Invocação (G9):** subprocess do CLI (`rag-sqlite` no PATH ou `rag_sqlite_root/rag_sqlite.py`) com `--db`, `--compact`, parse JSON stdout. **Não** `import rag_sqlite` como contrato de produto.

**Leitura do app DB (G4):** **nunca** `get_transcription()` até corrigido. Usar query com colunas **nomeadas**:

```sql
SELECT t.id, t.video_id, t.language, t.full_text, t.word_count,
       v.title, v.url, v.channel, v.video_id AS youtube_video_id
FROM transcriptions t
JOIN videos v ON t.video_id = v.id
WHERE t.id = ?
```

(ou `row_factory = sqlite3.Row` em qualquer SELECT).

### 3.5 Superfícies de consumo LLM

| Consumidor | Como usa a base |
|------------|-----------------|
| **Agente externo (principal)** | `rag-sqlite --db "$RAG_SQLITE_DB" --compact export-context "…" --top-k 8` + manifest para títulos |
| **Skill/playbook** | doc em down-youtube: playbook “memória YouTube” |
| **Chat GUI** | `remember(pergunta, video_scope=…)` |
| **CLI futura no app** | thin wrapper sobre o mesmo CLI |

Prova da visão (agente frio, sem UI):

```bash
export RAG_SQLITE_DB="$HOME/.youtube_transcriber/youtube_rag.sqlite"
rag-sqlite --db "$RAG_SQLITE_DB" --compact export-context \
  "o que X disse sobre Y?" --top-k 8 --min-score 0.15
# depois: enriquecer hits com rag_manifest.jsonl (transcription_id, title)
```

---

## 4. Modelo mental: “memória de longo prazo”

```text
┌─ Memória conversacional (Conversation ESAA) ─┐
│  o que agentes decidiram / tarefas / handoff   │
└────────────────────────────────────────────────┘
┌─ Memória de vídeos (este plano) ───────────────┐
│  o que foi dito em transcrições YouTube        │
│  retrieval sob demanda via rag-sqlite CLI      │
└────────────────────────────────────────────────┘
┌─ Chat sessions do app (SQLite app) ────────────┐
│  diálogos curtos por transcrição               │
└────────────────────────────────────────────────┘
┌─ Governança de execução (ESAA /home/elzobrito) ┐
│  claim/complete/review das tasks YT-LTM-*      │
└────────────────────────────────────────────────┘
```

Regras:

- **Não** indexar `chat_messages` no RAG no MVP.
- **Não** sincronizar para `.conversation-esaa` automaticamente.
- **Não** usar `down-youtube/.roadmap` (incompleto).

---

## 5. Integração no down-youtube (writer)

### 5.1 Gatilhos de escrita na memória

| Evento | Ação |
|--------|------|
| Transcrição salva/atualizada | enfileirar `pending` → worker com lock → project + CLI index; falha re-enfileira |
| Transcrição/vídeo apagado | enfileirar `forget` |
| Settings “Reindexar memória” | `index_library` + reconcile |
| Startup do app | `reconcile()` (não bloquear UI por muito tempo; progresso em background) |
| Restore backup app | rebuild projeções a partir do app DB |
| Mudança de embedding model | CLI `reindex --force` + novo fingerprint no report |

Falha de index **nunca** falha download/transcrição; fica na fila persistente.

### 5.2 Durabilidade (G5) — detalhe

| Mecanismo | Spec |
|-----------|------|
| Fila | `rag_index_queue.jsonl` ou tabela `rag_jobs` no app DB; campos: `transcription_id`, `op` (`index`/`forget`), `status`, `attempts`, `last_error`, `ts` |
| Lock | arquivo `rag_writer.lock` com timeout; um writer por data_dir |
| Atômico (md) | `*.md.tmp` → `os.replace` |
| Atômico (manifest) | rewrite completo em temp + replace **ou** append + compact periódico |
| Reconciliação | `S_app - S_rag` → reindex; `S_rag - S_app` → forget/prune; reprocessar `pending`/`error` com backoff |

### 5.3 Settings do app (chave de memória)

| Key | Default | Nota |
|-----|---------|------|
| `rag_enabled` | `1` | master |
| `rag_sqlite_cli` | `rag-sqlite` ou path do script | **CLI**, não import |
| `rag_db_name` | `youtube_rag.sqlite` | sob data_dir; exportar como `RAG_SQLITE_DB` |
| `rag_embedding_provider` | `ollama` | ou `hash` offline |
| `rag_embedding_model` | `embeddinggemma` | **≠** modelo de chat |
| `rag_top_k` | `8` | memória multi-vídeo |
| `rag_min_score` | `0.15` | |
| `rag_max_context_chars` | `16000` | budget para LLM |
| `rag_expand_neighbors` | `1` | se o CLI suportar |
| `rag_default_scope` | `library` | `library` \| `video` |
| `rag_index_on_save` | `1` | enfileira, não fire-and-forget |
| `rag_fallback_full_text` | `1` | só chat 1-vídeo |

### 5.4 Chat do app (cliente, não dono da memória)

- Default scope **vídeo atual** no ChatWindow.
- Toggle “buscar na biblioteca inteira”.
- Cada mensagem: `remember` → CONTEXT enriquecido → Ollama.
- Status: `Memória: N hits · backend · max_score`.
- Se 0 hits + fallback: full_text truncado **só** no scope vídeo.

### 5.5 Bug `get_transcription` (G4) — trabalho obrigatório

**Evidência (DB real, 2026-07-21):** `t.*` tem 12 colunas (0–11); vídeo começa no índice 12. O código mapeia `video_title=result[10]` (na prática `updated_at`), etc.

| Ação | Onde |
|------|------|
| Corrigir mapeamento **ou** migrar para `sqlite3.Row` / colunas nomeadas | `database.py` |
| Teste de regressão: título/url/canal batem com JOIN explícito | `tests/` |
| Bridge e GUI que usam `video_title` dependem do fix | chat, library, export |

Este fix pode ser task `YT-LTM-001` (impl) **antes** ou no **mesmo** PR do bridge, mas o bridge **não** chama a API quebrada.

### 5.6 Privacidade / git (G6)

Criar `.gitignore` no down-youtube (mínimo):

```gitignore
# runtime / portable data
data/
*.sqlite
*.sqlite3
*.db
*.db-journal
*.db-wal
*.db-shm

# RAG projections (nunca commitar corpus de usuário)
rag_corpus/
**/rag_manifest.jsonl
**/rag_index_queue.jsonl
**/rag_backfill_report.json
**/rag_writer.lock
**/rag_backup_meta.json

# caches
__pycache__/
.pytest_cache/
*.pyc
.venv/
venv/
```

Modo portátil: documentar que `./data/` é local e ignorado.

---

## 6. Contrato para LLMs externos (obrigatório no MVP)

1. **`docs/guides/youtube-long-term-memory.md`** com:
   - path padrão do DB e corpus
   - playbook: `health` → `stats` → `export-context`
   - **env canônico:** `RAG_SQLITE_DB` (opcional `RAG_SQLITE_CLI`)
   - como citar: hit → manifest → `transcription_id` / título
   - exemplo de system prompt (CONTEXT untrusted)
2. Snippet de skill (fase posterior): Grok/Codex “consultar memória YouTube”.
3. Envelope esperado (rag-sqlite):
   - Sucesso: `ok: true`, `context`, `hits[]` (`score`, `chunk_text`, `filename`, `source_path`, …)
   - Erro: `rag_sqlite.error.v1` tipado
4. Agente **não** inventa trechos se `hit_count == 0`.
5. Enriquecimento de citação é responsabilidade do **cliente** (bridge/playbook), não do motor.

---

## 7. Por que SQLite encaixa na visão

| Requisito LTM | Como atende |
|---------------|-------------|
| Persistência local | `youtube_rag.sqlite` |
| Crescimento incremental | upsert por `source_path` + hash |
| Consulta sob demanda | CLI query/export-context |
| Determinismo p/ agentes | JSON + fingerprint de embedding |
| Offline / teste | provider `hash` |
| Backup seguro do app | API `backup` + quick_check + hash |
| IDs com lacunas | aceite por **conjunto**, não por sequência |

---

## 8. Fases de entrega (ESAA em `/home/elzobrito`)

> **G1:** todas as tasks abaixo vivem em `esaa --root /home/elzobrito`.  
> IDs sugeridos: `YT-LTM-000` … (este plano = `YT-LTM-000`).  
> **Não** usar `DYT-LTM-*` no ESAA quebrado de `down-youtube`.

### Fase 0 — Spec da memória (`YT-LTM-000` · spec) — **este documento**

- Visão + paths canônicos + contrato agente + gaps G1–G9 fechados no plano.
- Critério: plano revisado e aprovado para execução das fases 1+.

### Fase 1 — Pré-requisitos de dados + backup + fix (`YT-LTM-001` · impl)

- Corrigir `get_transcription` (ou API Row) + testes
- Upgrade de backup: API SQLite + quick_check + hash (substituir/estender `utils/backup.py`)
- `.gitignore` (G6)
- **Proibido:** DROP/DELETE em massa no app DB

**Aceite:** testes de metadados; backup de go-live passa quick_check; git status não oferece DB/corpus.

### Fase 2 — Base de memória writer + backfill total (`YT-LTM-002` · impl) — **núcleo**

- `core/rag_bridge.py` via **CLI JSON** (G9)
- project atômico + manifest + fila + lock (G5)
- `backfill_all_transcriptions()` + `reconcile()`
- hook pós-`save_transcription` → enqueue
- defaults settings; `RAG_SQLITE_DB` no playbook
- relatório `rag_backfill_report.json`
- testes offline (`hash`) + **set equality** app vs RAG (G8)

**Aceite:**
1. App DB intacto (path; counts videos/transcriptions/chat).
2. `S_app == S_rag` (+ fingerprint/geração ativa).
3. CLI `export-context` multi-vídeo no corpus completo.
4. Hits enriquecíveis via manifest (`transcription_id`, título).

### Fase 3 — Superfície LLM externa (`YT-LTM-003` · impl/docs)

- guide playbook + env `RAG_SQLITE_DB`
- smoke `scripts/memory_smoke.sh`
- (opcional) skill Grok mínima

**Aceite:** playbook executável; JSON `ok` com hits; citação via manifest documentada.

### Fase 4 — Chat como cliente (`YT-LTM-004` · impl)

- chat_tab usa `remember`
- scope vídeo vs biblioteca
- fallback e status UI

**Aceite:** chat não despeja full_text quando há hits; não usa `get_transcription` quebrado.

### Fase 5 — Operação (`YT-LTM-005` · impl)

- Settings: health, reindex, paths, modelo embed
- prune órfãos; reconciliação manual
- backup story documentada

### Fase 6 — QA (`YT-LTM-006` · qa)

- testes, README, review approve, `esaa --root /home/elzobrito verify`

---

## 9. Critérios de aceite da visão (não só do chat)

1. **Não perda:** app DB preservado; backup pré-backfill com API + quick_check + hash.
2. **Cobertura 100%:** `S_app == S_rag` (conjuntos de `transcription_id`), não “sem buracos de ID”.
3. **Fingerprint/geração:** report registra embedding ativo; mismatch ⇒ reindex explícito.
4. **Persistência:** índice RAG sobrevive a reinício; fila reconcilia pendentes.
5. **Multi-vídeo:** query sem filtro usa a biblioteca completa.
6. **Consumo externo:** CLI rag-sqlite sem GUI; env `RAG_SQLITE_DB`.
7. **Citabilidade:** hits → manifest → `transcription_id` / título / URL (não só filename).
8. **Isolamento de schema:** dois SQLite; nenhum `settings` colidido.
9. **Fail-soft no writer:** falha de embed não quebra pipeline YouTube; fica na fila.
10. **Fail-closed no reader:** erro tipado JSON; zero hits ≠ alucinar.
11. **Integração:** bridge só via CLI JSON; monólito não é API importada.
12. **Governança:** tasks só em `/home/elzobrito`; verify ok.
13. **Privacidade:** `.gitignore` impede commit de DB/corpus portátil.

---

## 10. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| ESAA incompleto em down-youtube | Governar no home (G1) |
| Cópia de DB aberto corrompe backup | API `backup` + quick_check (G2) |
| Citar só filename sem título | manifest/lookup (G3) |
| Metadados errados no bridge | fix `get_transcription` + SELECT nomeado (G4) |
| Index async “some” | fila + lock + atômico (G5) |
| Commit acidental de corpus | `.gitignore` (G6) |
| Env inventado que o motor ignora | `RAG_SQLITE_DB` (G7) |
| Aceite frágil por sequência de IDs | set equality (G8) |
| Acoplamento ao monólito Python | CLI JSON (G9) |
| Confundir LTM com Conversation ESAA | paths e docs separados |
| CONTEXT como instrução | system prompt + untrusted |
| Modelo chat ≠ embed | settings e health separados |

---

## 11. Fora de escopo

- Fine-tune / gravação permanente nos weights do LLM  
- Unificar com `.conversation-esaa`  
- Servidor HTTP multi-user  
- Mesclar os dois SQLite sem redesign do rag-sqlite  
- Indexar áudio bruto (só texto de transcrição no MVP)  
- Substituir o catálogo do app pelo RAG DB  
- Parse de YAML front matter **dentro** do rag-sqlite no MVP (manifest cobre)  
- “Corrigir” IDs do SQLite para ficarem contíguos  

---

## 12. Ordem prática de build

1. Fechar `YT-LTM-000` (este plano) com review.  
2. `YT-LTM-001`: fix `get_transcription` + backup seguro + `.gitignore`.  
3. `YT-LTM-002`: bridge CLI + manifest + fila + backfill + set equality.  
4. Validar com CLI rag-sqlite multi-vídeo.  
5. Playbook/skill para agentes.  
6. Chat GUI como cliente.  
7. Settings/ops + QA.

---

## 13. Resumo executivo

| Pergunta | Resposta |
|----------|----------|
| O que é “a base”? | Verdade: `youtube_transcriber.db`. Projeção: `youtube_rag.sqlite` + `rag_corpus/` + manifest |
| Base atual se perde? | **Não.** Backup API + app intocado; RAG aditivo |
| Transcrições existentes? | **Todas** (22 hoje) no backfill; aceite por **conjunto** de IDs |
| Onde governa? | **`/home/elzobrito`**, não o ESAA incompleto do repo |
| Como o bridge fala com o RAG? | **CLI JSON** (`RAG_SQLITE_DB`), não import do monólito |
| Como citar título/id? | **Manifest/lookup** (motor não lê YAML) |
| MVP mínimo? | fix metadados + backup seguro + backfill 100% + `export-context` multi-vídeo + manifest |

**Mudança em relação ao plano anterior:** além do eixo “base de memória para LLMs”, o plano incorpora explicitamente G1–G9 (governança home, backup SQLite real, metadados via manifest, fix de índices, durabilidade, gitignore, env canônico, aceite por sets, CLI como contrato).
