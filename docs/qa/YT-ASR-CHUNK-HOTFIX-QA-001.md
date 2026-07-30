# QA — HF-ISS-CHUNK-HALLUCINATION-002

## Objetivo

Validar a correção do chunking anti-alucinação do Whisper no áudio real
`8TjK-s0468w.wav` (5.091,927 s), que originou a tarefa `YT-CHUNK-001`.

## Ambiente

- Data: 2026-07-30
- Whisper.cpp: 1.9.1
- ASR: `ggml-small.bin`
- Idioma: `portuguese`
- Decode: beam 1, best-of 1, 8 threads
- GPU: NVIDIA GeForce GTX 1050 Ti, 4 GiB
- VAD validado: Silero v6.2.0 GGML, sha256
  `2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987`

## Matriz real

Cada perfil transcreveu o áudio completo. “Loop” significa três ou mais
segmentos consecutivos com o mesmo texto normalizado.

| Perfil | Tempo | Segmentos | 8-gramas repetidos | Segmentos em loops | Duração de loops | Maior loop |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 min legado | 401,5 s | 2.034 | 250 | 26 | 66,0 s | 58,0 s |
| 10 min + overlap/silêncio | 595,3 s | 1.958 | 1.055 | 135 | 284,0 s | 202,0 s |
| 5 min + overlap/silêncio | 633,6 s | 1.665 | 1.236 | 154 | 331,0 s | 146,0 s |
| 5 min + VAD + contexto 0 + suppress-nst | 819,7 s | 1.366 | 149 | 17 | 64,5 s | 32,9 s |
| Perfil anterior + proteção anti-loop no merge | determinístico | 1.356 | 42 | 0 | 0 s | 0 s |

Conclusões:

1. Reduzir chunks isoladamente piorou este caso real; reinicializações do modelo
   Small em regiões ambíguas criaram novos loops.
2. O conjunto VAD + `--max-context 0` + `--suppress-nst` reduziu o maior loop
   em 43% e os 8-gramas repetidos em 40% contra o perfil legado, mas dobrou o
   tempo de processamento.
3. A proteção conservadora do merge, que mantém duas ocorrências exatas e
   elimina somente a terceira contígua em diante, removeu os três loops
   remanescentes no replay determinístico e reduziu 8-gramas repetidos em 83%
   contra o legado.
4. Portanto, o default aprovado é o conjunto completo; chunk de 5 minutos sem
   hardening não deve ser anunciado como correção suficiente.

## Cobertura automatizada

- threshold padrão de 10 minutos e chunk de 5 minutos;
- ranges físicos sobrepostos e ranges temporais exclusivos;
- corte deslocado para baixa energia antes da fronteira nominal;
- merge e deduplicação por timestamps no overlap;
- fallback textual por prefixo/sufixo;
- limite de duas repetições exatas contíguas;
- flags `--vad`, `--vad-model`, `--vad-max-speech-duration-s`,
  `--vad-samples-overlap`, `--max-context` e `--suppress-nst`;
- autodetecção de modelo Silero ao lado do modelo Whisper;
- split/merge, cancelamento, progresso e limpeza de temporários preexistentes.

Resultado final automatizado: `163 passed`, 15 warnings de depreciação
FastAPI/Starlette já existentes; `pip check` e `git diff --check` aprovados.

## Comando do benchmark

```bash
PYTHONPATH=. .venv/bin/python tests/asr_chunk_benchmark.py \
  /mnt/backup-ssd/Downloads/Transcricoes/8TjK-s0468w.wav \
  --cli /home/elzobrito/.local/opt/whisper.cpp/bin/whisper-cli \
  --model /home/elzobrito/desenvolvimento/whisper.cpp/models/ggml-small.bin \
  --language portuguese \
  --output-dir /tmp/down-youtube-asr-chunk-benchmark \
  --profiles 30m 10m 5m
```

Para o perfil endurecido, adicionar:

```text
--profiles 5m --max-context 0 --suppress-nst \
--vad-model <silero-vad-ggml.bin>
```

## Limitações

- O benchmark mede repetição/hallucinação, não WER completo, pois não há
  transcrição humana de referência para as 84,9 min.
- VAD e contexto zerado podem alterar palavras próximas a pausas; a transcrição
  continua sujeita à revisão humana.
- Se nenhum modelo VAD compatível for encontrado, o runtime registra aviso e
  segue sem VAD; nesse caso a proteção anti-loop ainda evita repetição exata,
  mas a qualidade deve ser considerada degradada.
