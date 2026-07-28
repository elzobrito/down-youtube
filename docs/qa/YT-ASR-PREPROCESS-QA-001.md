# YT-ASR-PREPROCESS-QA-001 — QA funcional e benchmark dos presets ASR

**Workspace:** `/home/elzobrito/desenvolvimento/down-youtube`  
**Data:** 2026-07-28  
**Runner:** `human-terminal` / actor `agent-qa`  
**Tasks cobertas:** `YT-ASR-PREPROCESS-000`…`003`  
**Decisão de gates WER:** **APROVADO**

---

## 1. Escopo

Validar independentemente:

| Área | Evidência |
|------|-----------|
| Presets off/light/speech, inválido, fallback, corrupt/cancel, limpeza, hashes | `tests/test_audio_preprocess.py` |
| Proveniência em DB | `test_save_transcription_provenance`, `tests/test_get_transcription.py` |
| Snapshot de job/batch + legado → off | `tests/test_app_jobs.py` |
| Worker 1× preprocess antes do hash | `test_worker_applies_preprocess_once_before_hash` + caminhos em `test_audio_quality.py` |
| Smoke FFmpeg real | `test_smoke_ffmpeg_light_and_speech` |
| Benchmark WER jfk + degradados | `tests/asr_preprocess_benchmark.py` + `tests/fixtures/jfk-reference.txt` |

---

## 2. Comandos e resultados

### 2.1 Suíte pytest

```bash
.venv/bin/python -m pytest -q
```

**Resultado:** `129 passed, 15 warnings` (warnings FastAPI/Starlette pré-existentes).

### 2.2 compileall

```bash
.venv/bin/python -m compileall -q app core api cli database.py config.py main.py
```

**Resultado:** `compileall_ok` (exit 0).

### 2.3 pip check

```bash
.venv/bin/pip check
```

**Resultado:** `No broken requirements found.`

### 2.4 git diff --check

```bash
git diff --check
```

**Resultado:** trailing whitespace no plan corrigido; check limpo no artefato revisado.

### 2.5 esaa verify

```bash
python -m esaa --root . verify
```

**Resultado:** `verify_status: ok` (seq 505 no claim da QA; revalidado após complete).

---

## 3. Versões

| Componente | Versão / path |
|------------|----------------|
| FFmpeg | 7.0.2-static (`ffmpeg` / `~/.local/bin/ffmpeg`) |
| whisper-cli | whisper.cpp **1.9.1** (`~/.local/opt/whisper.cpp/bin/whisper-cli`) |
| Modelo | `~/desenvolvimento/whisper.cpp/models/ggml-small.bin` |
| Sample | `~/desenvolvimento/whisper.cpp/samples/jfk.wav` (16 kHz mono, ~11 s) |
| Referência | `tests/fixtures/jfk-reference.txt` |
| CUDA | GTX 1050 Ti (visível no init ggml; decode settings fixos no bench: `-bs 1 -bo 1 -t 4 -l en`) |

Filtros confirmados no FFmpeg local: `afftdn`, `loudnorm`, `dynaudnorm`.

---

## 4. Matriz funcional (resumo)

### 4.1 AudioProcessor

| Caso | Resultado |
|------|-----------|
| `off` sem FFmpeg, path/bytes/hashes iguais | pass |
| `light` cmdline highpass=80, lowpass=7600, loudnorm, 16k mono | pass |
| `speech` fallback → light quando afftdn falha | pass |
| `light` falha → original, applied=off | pass |
| output corrompido não substitui WAV | pass |
| cancel antes do FFmpeg | pass |
| temp no mesmo dir + limpeza | pass |
| smoke real light/speech | pass |

### 4.2 Worker / jobs

| Caso | Resultado |
|------|-----------|
| Streaming path: 1× preprocess, hash = post | pass |
| HQ keep_audio usa traditional (regessão) | pass |
| Streaming sem keep_audio (regessão) | pass |
| Job freeze snapshot preset | pass |
| Batch snapshot uniforme | pass |
| Job legado sem options_json → off | pass |
| Proveniência em `save_transcription` / `get_transcription` | pass |

### 4.3 Smoke formato

Com FFmpeg real: saída PCM s16le, 16 kHz, mono; sem `*.asrprep.tmp* residual`.

---

## 5. Benchmark WER

### 5.1 Comando

```bash
.venv/bin/python tests/asr_preprocess_benchmark.py
```

### 5.2 Tabela WER (%)

| Caso | off | light | speech |
|------|-----|-------|--------|
| clean | 0.00 | 0.00 | 0.00 |
| stationary_noise | 59.09 | **50.00** | 54.55 |
| tonal_rhythm | 0.00 | 0.00 | 0.00 |

**Tempo total:** ~15 s (9 passes whisper small + preprocess).

### 5.3 Gates (spec)

| Gate | Critério | Resultado |
|------|----------|-----------|
| Clean | regressão light/speech vs off ≤ 5 pp | **OK** (0.00 pp) |
| Degradados | mediana do melhor(light,speech) **<** mediana off | **OK** (0.25 < 0.295) |
| **Aprovação** | ambos | **APROVADO** |

Notas:

- `stationary_noise`: light reduziu WER 59.09 → 50.00; speech 54.55 (também melhor que off).
- `tonal_rhythm` com a cama tonal usada **não** piorou o jfk (WER 0 em todos os presets) — small+jfk ainda robusto; o gate de mediana ainda passa por causa do ruído estacionário.
- Filtros **não** separam música alta nem vozes sobrepostas; ganhos sintéticos ≠ garantia em shows ao vivo.

### 5.4 Limitações honestas

1. Benchmark sintético (ruído/tom gerados), não corpus real de vídeos do usuário.
2. Modelo **small**; medium/large devem se comportar melhor em áudio sujo (orientação de produto, sem troca automática).
3. `tonal_rhythm` não stressou o WER neste sample curto — não interpretar como “filtros resolvem música”.
4. Default de produto permanece **`off`** (sem regressão de UX).

---

## 6. Decisão QA

| Item | Status |
|------|--------|
| Funcional / regressão pytest | pass |
| Smoke FFmpeg | pass |
| Gates WER | **approved** |
| Issue aberta por falha de gate | **não** (gates OK) |
| Review mode | regression → approve |

---

## 7. Artefatos

- `tests/asr_preprocess_benchmark.py`
- `tests/fixtures/jfk-reference.txt`
- `docs/qa/YT-ASR-PREPROCESS-QA-001.md` (este arquivo)
- Spec: `docs/plans/PLAN-asr-audio-preprocess.md`

---

**Fim do relatório QA.**
