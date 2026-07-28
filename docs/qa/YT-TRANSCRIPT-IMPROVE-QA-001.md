# QA — aprimoramento de transcrições com Phi-4 Mini

Data: 2026-07-28  
Tarefa: `YT-TRANSCRIPT-IMPROVE-003`  
Modelo do smoke: `phi4-mini:latest` via Ollama local

## Resultado

Gate aprovado. O fluxo mantém o original imutável, não expõe drafts a busca,
Chat IA ou RAG, bloqueia mudanças lexicais desconhecidas por padrão e só troca
os consumidores após aprovação humana.

## Testes automatizados

- Suíte focada: `23 passed`.
- Suíte completa: `152 passed`, com 15 avisos de depreciação preexistentes em
  FastAPI/Starlette.
- Cliente Ollama: JSON válido, JSON inválido, divergência de schema, modelo
  ausente/HTTP 404 e timeout.
- Motor: chunks com contexto, cobertura integral sem IDs duplicados, retry
  único, cancelamento antes da primeira chamada e entre chunks, fallback sem
  timestamps, outtake recuperável e proteção contra paráfrase.
- Banco e integração: migração idempotente, aprovação atômica, múltiplas
  revisões, rejeição, desativação, exclusão em cascata explícita, hash estável
  do original, versões efetivas, busca, estatísticas, Chat IA, RAG e Markdown.

Comandos principais:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_ollama_client.py \
  tests/test_transcript_improver.py \
  tests/test_transcription_revisions.py \
  tests/test_transcript_improvement_integration.py

PYTHONPATH=. .venv/bin/python -m pytest -q
```

## Migração sobre cópia do banco real

A migração foi executada duas vezes sobre uma cópia temporária do banco local
com 39 transcrições:

- tabela `transcription_revisions`: criada;
- índice parcial único `idx_transcription_revision_active`: criado;
- revisões iniciais: 0;
- hash agregado de `full_text + segments_json` antes e depois:
  `1f67596a54f3c5eb0ff72ba2933fab74ca972d3257d931c0e5cca47c03a42928`;
- resultado: fontes originais inalteradas.

O banco real não foi migrado nem modificado durante este smoke; a aplicação
executará a migração idempotente em sua inicialização normal.

## Smoke Tkinter

Uma raiz Tk 8.6.17 foi criada no display local. A Biblioteca foi instanciada
com banco temporário, uma transcrição foi selecionada e a janela de revisão foi
aberta e fechada com sucesso (`TK_LIBRARY_SMOKE_OK`).

O cancelamento visual usa um `Event`; a chamada corrente termina e o motor
interrompe antes do próximo chunk. O teste automatizado confirma que nenhum
segundo request é iniciado. A persistência ocorre somente após todos os chunks,
portanto cancelamento ou erro não cria revisão parcial.

## Smoke real Phi-4 Mini

Fonte: sete segmentos reais da transcrição 38, vídeo “Burlando Proxies e
Firewalls | Introdução a Redes Parte 5 - SSH”, incluindo ocorrências de
`CalCey`.

| Métrica | Resultado |
| --- | ---: |
| Caracteres centrais | 671 |
| Segmentos centrais | 7 |
| Chunks | 1 |
| Duração total | 94,728 s |
| Tokens de prompt | 474 |
| Tokens gerados | 648 |
| Propostas | 10 |
| Correções validadas selecionadas | 4 |
| Mudanças lexicais bloqueadas | 6 |
| Outtakes | 0 |
| IDs recebidos/únicos | 7/7 |

Hashes da entrada:

- texto: `d7ba64429d282e6cc565d3913d74c403af0768742fa5b2a9d0fbeeaee6be2927`;
- segmentos:
  `48699cd3e89c31448e3baef35eb95bea600ed482de3e7c790fb2fe1d04e910a9`.

Ambos permaneceram iguais após o smoke, que não persistiu revisão.

As três ocorrências contextuais de `CalCey` foram corrigidas
deterministicamente para `cowsay`. O modelo tentou seis alterações lexicais,
incluindo paráfrases e reversões para `CalCey`; todas ficaram desmarcadas e
nenhuma entrou no texto fiel. Erros não cobertos por regra segura, como
`cosme` e `Ask +`, foram preservados para decisão humana.

Não foi calculado WER: o trecho real não possui referência humana alinhada.
Este benchmark mede segurança do pós-processamento, cobertura e latência, não
qualidade ASR absoluta.

## Limitações aceitas

- Neste hardware, 94,728 s para 671 caracteres é seguro, mas lento; o modal
  precisa continuar mostrando progresso e cancelamento.
- O modelo ainda propõe paráfrases incorretas. A validação conservadora e a
  revisão humana são requisitos permanentes, não salvaguardas temporárias.
- O glossário corrige somente padrões comprovados. Termos ambíguos permanecem
  como no original ou como sugestão desmarcada.
- Outtakes são decisão editorial do modelo e começam selecionados no draft,
  porém sempre podem ser restaurados antes da aprovação e continuam no
  original imutável.
