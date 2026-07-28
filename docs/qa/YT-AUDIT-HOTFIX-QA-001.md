# YT-AUDIT-HOTFIX-QA-001 — QA integrada dos hotfixes da auditoria

**Workspace:** `/home/elzobrito/desenvolvimento/down-youtube`  
**Data:** 2026-07-28  
**Runner:** `human-terminal` / actor `agent-qa`  
**ESAA last_event_seq (claim QA):** 326  

## Escopo

Validar os cinco hotfixes da auditoria e o registro de supersessão do hotfix automático incorreto:

| Task | Defeito | Status esperado |
|------|---------|-----------------|
| YT-RAG-QUEUE-HOTFIX-001 | Fila RAG concorrente / claim | done |
| YT-JOB-RECOVERY-HOTFIX-001 | Running órfão bloqueia fila | done (hotfix efetivo) |
| HF-ISS-YT-JOB-RESULT-001 | Perda de vínculo com transcrições | done |
| HF-ISS-YT-MULTISITE-ID-001 | Colisão cross-site de `video_id` | done |
| HF-ISS-YT-AUDIO-HQ-001 | Streaming sem arquivo HQ | done |
| HF-ISS-YT-JOB-RECOVERY-001 | Hotfix automático com scope errado | superseded → `request_changes` |

## Comandos e resultados

### 1. Suíte completa

```bash
.venv/bin/python -m pytest -q
```

**Resultado:** `108 passed, 15 warnings` (warnings apenas depreciação FastAPI/Starlette, pré-existentes).

### 2. Reproduções determinísticas por defeito

| Defeito | Testes-chave | Resultado |
|---------|--------------|-----------|
| RAG fila | `test_concurrent_enqueue_during_process_not_lost`, `test_rag_claim_atomic_two_claimers`, `test_rag_stale_running_recovered`, `test_legacy_jsonl_import_idempotent` | pass |
| Job recovery | `test_orphan_running_failed_on_startup_then_queued_runs`, `test_claim_queued_is_atomic`, `test_restart_recovery_then_claim` | pass |
| Job results | `test_job_persists_ordered_results_from_worker`, `test_job_singular_result_when_one`, `test_job_results_list_exposed_for_batch` | pass |
| Multisite ID | `test_normalize_source_site_youtube_variants`, `test_cross_site_same_video_id_separate_rows` | pass |
| Audio HQ | `test_best_quality_keep_audio_skips_streaming`, `test_streaming_still_used_without_keep_audio` | pass |

### 3. Migração SQLite em banco temporário preexistente

Script ad-hoc: criou `videos` + `settings` com 2 linhas (YouTube e Vimeo, mesmo `video_id`), rodou `init_database()`, verificou:

- contagem de vídeos permanece 2 (dados preservados);
- tabelas `rag_index_jobs` e `jobs` criadas;
- `add_video` cross-site não mescla identidades.

**Resultado:** `migration_smoke_ok`.

### 4. compileall

```bash
.venv/bin/python -m compileall -q app core api cli database.py config.py main.py
```

**Resultado:** `compileall_ok` (exit 0).

### 5. pip check

```bash
.venv/bin/pip check
```

**Resultado:** `No broken requirements found.`

### 6. git diff --check

```bash
git diff --check
```

**Resultado:** exit 0 (sem whitespace errors).

### 7. esaa verify

```bash
python -m esaa --root . verify
```

**Resultado:** `verify_status: ok` (evento 326 no momento do claim QA; revalidar após complete).

## Evidências de correção (resumo técnico)

1. **RAG:** `process_queue` usa `claim_next_rag_job` (BEGIN IMMEDIATE); enqueue concorrente vira linha SQLite e não é apagado por rewrite de JSONL; import legado JSONL com flag `rag_queue_jsonl_imported`.
2. **Job recovery:** `fail_orphan_running_jobs` + `reconcile_jobs_on_startup` no start do loop; `claim_next_queued_job` atômico.
3. **Job results:** `TranscriberWorker.produced_results` a partir de `save_transcription`; `jobs.result_json` + campos singulares só com 1 item; API `to_dict()` expõe `results`.
4. **Multisite:** `normalize_source_site` + lookup `(source_site, video_id)`.
5. **Audio HQ:** `best_quality && keep_audio` força pipeline tradicional (archive M4A/Opus + WAV).

## Decisão QA

**Aprovar** a integração dos cinco hotfixes válidos.  
O hotfix automático `HF-ISS-YT-JOB-RECOVERY-001` permanece superseded por `YT-JOB-RECOVERY-HOTFIX-001` (review `request_changes` para não promover o scope incorreto).

## Checklist de aceitação da tarefa QA

- [x] `.venv/bin/python -m pytest -q` conclui com sucesso (108 passed)
- [x] Testes determinísticos cobrem os cinco defeitos (concorrência e restart inclusos)
- [x] Migrações validadas em DB temporário preexistente com preservação de dados
- [x] `compileall`, `pip check`, `git diff --check` sem erro
- [x] `esaa verify` ok
- [x] Este documento registra comandos, resultados e evidências
