# Plano: memória de longo prazo (RAG) no down-youtube

Documento canônico para análise/execução:

**[docs/plans/PLAN-youtube-ltm-rag.md](docs/plans/PLAN-youtube-ltm-rag.md)**

**Status:** revisado pré-execução (2026-07-21) — gaps G1–G9 incorporados.  
**Governança ESAA:** `esaa --root /home/elzobrito` (task `YT-LTM-000` = este plano).  
**Não usar** o ESAA incompleto em `down-youtube/.roadmap` (`roadmap_missing`).

Repos relacionados:
- App / writer: este repositório (`down-youtube`)
- Retrieval (CLI JSON): `/home/elzobrito/desenvolvimento/rag-sqlite`
- App DB (não alterar destrutivamente): `~/.youtube_transcriber/youtube_transcriber.db` (22 transcrições com texto em 2026-07-21)

Pré-requisitos de execução (resumo):
1. Backup via API SQLite + `quick_check` + hash (não cópia simples)
2. Manifest/lookup para `transcription_id`/título (motor não lê YAML)
3. Corrigir `get_transcription()` antes do bridge depender dela
4. Fila persistente + lock + writes atômicos
5. `.gitignore` para `data/` / sqlite / corpus
6. Env canônico: `RAG_SQLITE_DB`
7. Aceite por igualdade de conjuntos de IDs (+ fingerprint)
8. Bridge via CLI JSON do rag-sqlite

Próximo passo após approve de `YT-LTM-000`: criar/claim `YT-LTM-001` (fix + backup + gitignore).
