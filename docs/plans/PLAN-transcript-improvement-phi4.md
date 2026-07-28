# Plano canônico — aprimoramento de transcrições com Phi-4 Mini

**Task:** `YT-TRANSCRIPT-IMPROVE-000`  
**Status do plano:** especificação executável  
**Modelo padrão:** `phi4-mini:latest`

## 1. Objetivo e invariantes

Adicionar à Biblioteca um fluxo local de revisão pós-ASR que produza:

1. uma transcrição fiel corrigida, mantendo segmentos e timestamps;
2. uma versão de estudo em Markdown, derivada do texto fiel;
3. um rascunho persistido e revisável antes de se tornar ativo.

Invariantes:

- `transcriptions.full_text` e `transcriptions.segments_json` são a fonte bruta e nunca são reescritos;
- rascunhos não alimentam busca, Chat IA, exports padrão nem RAG;
- somente uma revisão aprovada pode estar ativa por transcrição;
- comandos encontrados são apenas texto e nunca são executados;
- mudança lexical desconhecida nunca é aplicada automaticamente;
- falha ou cancelamento descarta o resultado parcial e preserva a fonte bruta.

## 2. Estado observado e decisão de segurança

O Ollama local possui `phi4-mini:latest` (3,8B, Q4). Dois probes com JSON
estruturado confirmaram compatibilidade, mas o modelo também parafraseou
indevidamente: interpretou `cowsay` como “sapatos” e alterou um comando falado.

Consequentemente, o modelo atua como proponente. O aplicativo:

- aplica automaticamente somente pontuação, caixa, espaços e regras
  contextuais conhecidas;
- transforma alterações lexicais desconhecidas em sugestões desmarcadas;
- mostra todas as remoções de outtake antes da aprovação;
- valida cobertura, ordem e unicidade dos segmentos.

## 3. Persistência

Criar a tabela `transcription_revisions`:

| Campo | Semântica |
|---|---|
| `id` | PK |
| `transcription_id` | FK lógica para a fonte bruta |
| `revision_number` | sequência por transcrição |
| `status` | `draft`, `approved` ou `rejected` |
| `is_active` | 0/1, com índice único parcial |
| `model` | modelo efetivamente usado |
| `prompt_version` | `transcript-improve-v1` |
| `glossary_version` | `technical-pt-v1` |
| `source_text_sha256` | hash do texto bruto |
| `source_segments_sha256` | hash JSON canônico dos segmentos |
| `improved_text` | transcrição fiel compilada |
| `improved_segments_json` | segmentos fiéis corrigidos |
| `study_markdown` | versão editorial derivada |
| `proposals_json` | correções, sugestões, comandos e outtakes |
| `decisions_json` | seleção efetivamente aprovada |
| `outtakes_json` | segmentos removidos e justificativas |
| `word_count` | palavras da revisão |
| `chunk_count` | chunks concluídos |
| `usage_json` | contagens e duração reportadas pelo Ollama |
| `created_at`, `updated_at`, `approved_at` | auditoria |

Restrições:

- `UNIQUE(transcription_id, revision_number)`;
- índice único parcial para `is_active = 1`;
- aprovação em `BEGIN IMMEDIATE`: desativa a revisão anterior e ativa somente o
  draft escolhido;
- rejeição nunca altera a revisão ativa;
- desativação explícita restaura o original como texto efetivo;
- exclusão da transcrição remove suas revisões explicitamente.

`get_transcription()` mantém `full_text` e `segments` brutos e acrescenta:

- `active_revision`;
- `effective_text`;
- `effective_segments`;
- `study_markdown`.

Busca, estatísticas, Chat IA e RAG usam `effective_*`, com fallback para a fonte
bruta. O RAG projeta o texto fiel, registra `revision_id` no front matter e é
reenfileirado após aprovar ou desativar uma revisão.

## 4. Cliente Ollama

Preservar `OllamaClient.chat()` e adicionar uma chamada JSON não streaming:

- endpoint `/api/chat`;
- `stream=false`;
- `format` igual ao JSON Schema da resposta;
- `temperature=0`;
- `seed=42`;
- `num_ctx=8192`;
- `keep_alive=10m`;
- timeout de 180 segundos;
- erro HTTP, timeout, modelo ausente, conteúdo vazio ou JSON inválido geram
  exceção, nunca texto de erro misturado à resposta.

Adicionar em Configurações `transcript_improvement_model`, padrão
`phi4-mini:latest`, independente de `ollama_model`.

## 5. Chunking e contrato do modelo

Normalizar cada segmento bruto para:

```json
{"id": "seg-000001", "start": 0.0, "end": 4.2, "text": "..."}
```

Agrupar segmentos centrais até aproximadamente 6.000 caracteres. Incluir um
segmento anterior e um posterior como `context_only`; o modelo deve devolver
somente IDs centrais. Registros sem segmentos são quebrados por sentenças e
recebem IDs sintéticos, sem inventar timestamps.

Contrato por chunk:

```json
{
  "segments": [
    {
      "id": "seg-000001",
      "corrected_text": "...",
      "paragraph_break_after": false,
      "remove_as_outtake": false,
      "outtake_reason": "",
      "section_title": "",
      "commands": [
        {"text": "ssh -D 1337 -q -C -N ...", "dangerous": false}
      ]
    }
  ]
}
```

Cada chunk pode ser tentado duas vezes. A resposta precisa conter exatamente os
IDs centrais, na ordem original. Falha repetida encerra toda a operação sem
persistir revisão parcial. Cancelamento é verificado antes e depois de cada
chamada.

## 6. Normalização e validação

O glossário contextual `technical-pt-v1` cobre, inicialmente:

- `calcei`, `calcê`, `CalCey` → `cowsay`;
- `digital ouxa`, `digital ouça` → `DigitalOcean`;
- variantes contextuais de `local host` → `localhost`, com porta somente quando
  pronunciada;
- variantes de `daemon` e `sshd` somente em contexto de processos/SSH;
- `coppe peixe`, `cop peixe` → `copy-paste`;
- `nude`, `node JTS` → `Node.js` somente em contexto de runtime JavaScript;
- `/etc/ssh/sshd_config` somente quando o caminho completo estiver evidenciado;
- flags SSH e portas somente quando todos os operandos necessários existirem.

O validador compara a saída com a base já normalizada:

- ignora pontuação, caixa e whitespace para verificar preservação semântica;
- aceita automaticamente substituições que correspondam a uma regra contextual;
- converte demais inserts/deletes/replaces em propostas desmarcadas;
- reverte a versão segura para o texto anterior quando houver paráfrase;
- marca comandos destrutivos, em especial `sudo rm -rf /`;
- permite remoção automática do rascunho apenas para segmentos inteiros marcados
  como outtake; remoção parcial vira sugestão.

Correções validadas e outtakes começam selecionados no diff. Sugestões
desconhecidas começam desmarcadas. A compilação final aplica a seleção do usuário.

## 7. Markdown de estudo

O Markdown não é uma segunda paráfrase. Ele é montado deterministicamente a
partir dos segmentos fiéis escolhidos:

- títulos propostos organizam intervalos de IDs;
- parágrafos seguem `paragraph_break_after`;
- comandos validados são exibidos em blocos cercados;
- o restante do conteúdo é preservado na mesma ordem;
- outtakes desmarcados permanecem; outtakes selecionados são omitidos.

O texto fiel, não o Markdown, alimenta busca, Chat IA e RAG.

## 8. Biblioteca

Adicionar `Aprimorar IA` ao lado de `Chat IA` e ao menu contextual.

Fluxo:

1. validar seleção, conexão e presença do modelo;
2. abrir progresso modal e iniciar thread daemon;
3. desabilitar nova execução para a mesma transcrição;
4. atualizar progresso por chunk via `after(0, ...)`;
5. permitir cancelamento após a chamada atual;
6. persistir o draft somente após todos os chunks válidos;
7. abrir automaticamente a janela de revisão.

A janela de revisão apresenta:

- original e proposta lado a lado;
- lista selecionável com categoria, trecho original, proposta e razão;
- badges para `validada`, `sugestão`, `outtake` e `comando perigoso`;
- preview recompilado ao mudar seleções;
- `Aprovar` e `Rejeitar`.

Após aprovação, o preview da Biblioteca oferece `Original`, `Aprimorada` e
`Estudo`, selecionando `Aprimorada` por padrão. Copiar, abrir, TXT, DOCX e PDF
usam a versão exibida. SRT/VTT usam os segmentos fiéis da revisão ativa. O menu
Exportar ganha Markdown. Uma ação `Usar original` desativa a revisão ativa.

## 9. Critérios de qualidade

- hash do texto e dos segmentos brutos idêntico antes/depois de gerar, rejeitar,
  aprovar e desativar;
- 100% dos IDs centrais cobertos, sem duplicação ou reordenação;
- zero mudança lexical desconhecida aplicada automaticamente;
- `calcei/CalCey` pode virar `cowsay`, nunca “sapatos”;
- `node JTS` pode virar `Node.js`, sem explicações inventadas;
- comandos só são materializados quando seus componentes estão presentes;
- drafts nunca aparecem em busca, Chat IA, exports padrão ou RAG;
- aprovação e desativação atualizam consumidores e enfileiram nova projeção RAG;
- UI permanece responsiva e cancelável;
- testes offline e suíte completa passam;
- smoke local registra duração, chunks, propostas bloqueadas, outtakes e
  limitações honestas.

## 10. Tarefas ESAA

| Task | Kind | Dependências | Resultado |
|---|---|---|---|
| `YT-TRANSCRIPT-IMPROVE-000` | spec | — | esta especificação |
| `YT-TRANSCRIPT-IMPROVE-001` | impl | 000 | banco, Ollama, motor, testes |
| `YT-TRANSCRIPT-IMPROVE-002` | impl | 001 | Biblioteca, Settings, exports, Chat/RAG |
| `YT-TRANSCRIPT-IMPROVE-003` | qa | 001, 002 | regressões, smoke e relatório |

Cada tarefa segue `claim`, `complete`, `review` em invocações separadas, com
`python -m esaa --root . verify` após toda escrita.
