# QA dos hotfixes pós-review do down-youtube

- Task: `YT-REVIEW-FINDINGS-QA-001`
- Data: 2026-07-27
- Resultado: aprovado
- Hotfixes validados: `YT-RAG-RETRY-HOTFIX-001`, `YT-JOB-LEASE-HOTFIX-001` e `YT-MULTISITE-NORMALIZE-HOTFIX-001`

## Resultado por achado

1. **Job RAG em erro monopoliza a fila** — corrigido. Jobs `queued` têm prioridade; jobs `error` só voltam a ser elegíveis após `next_attempt_at` e abaixo de `max_attempts`. A reprodução confirmou que o job posterior conclui enquanto o erro entra em backoff.
2. **Startup encerra jobs ainda ativos** — corrigido. O claim persiste `worker_id` e `heartbeat_at`; o startup preserva leases recentes e recupera apenas heartbeat ausente ou expirado. A renovação é restrita ao owner.
3. **Default YouTube corrompe identidade multisite** — corrigido. `source_site` omitido é inferido da URL, e uma origem conhecida não é sobrescrita por default.
4. **Migração deixa variantes legadas sem normalização** — corrigido. A migração canoniza valores existentes, incluindo `Youtube`, variantes de extractor e hosts equivalentes, antes do lookup composto.

## Evidências

- `pytest -q -p no:cacheprovider`: **116 passed**, 15 avisos de depreciação não bloqueantes.
- Regressões focadas: **7 passed** em 0,96 s:
  - fairness/backoff e limite de tentativas RAG;
  - lease fresca, lease expirada e heartbeat por owner;
  - duplicata Vimeo sem origem explícita;
  - migração SQLite da variante legada `Youtube` sem nova linha.
- `python -m compileall -q app api core gui tests utils config.py database.py main.py`: aprovado.
- `pip check`: `No broken requirements found.`
- `git diff --check`: aprovado, sem erros.
- `python -m esaa --root . --runner codex verify`: `verify_status=ok` antes do fechamento da QA.

## Observações

Os 15 avisos são depreciações já identificadas em Starlette/FastAPI e não afetam os critérios destes hotfixes. Nenhum acesso de rede foi necessário; as reproduções usam bancos temporários e são determinísticas.
