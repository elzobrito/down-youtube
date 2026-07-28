# PLAN: Pré-processamento de áudio para ASR (Whisper)

> **Destino canônico:** `docs/plans/PLAN-asr-audio-preprocess.md`
> **Workspace:** `~/desenvolvimento/down-youtube`
> **Data da revisão ESAA:** 2026-07-28
> **Task:** `YT-ASR-PREPROCESS-000` (spec, retrospective)

---

## 0. Aviso retrospectivo (obrigatório)

| Fato | Detalhe |
|------|---------|
| Commit pré-existente | `62791de` — *docs: add PLAN-asr-audio-preprocess for noisy/music ASR* |
| Como surgiu | Documento de plano escrito e commitado **fora** do fluxo ESAA formal de claim/complete |
| O que o ESAA **não** fez | O ESAA **não** criou, aprovou nem governou a geração do commit `62791de` |
| O que esta task faz | **Registro retrospectivo** + reescrita da spec com decisões de produto, invariantes Codex, tasks executáveis e sequência claim/complete/review |

Este arquivo, na revisão sob `YT-ASR-PREPROCESS-000`, **substitui** o rascunho de `62791de` como especificação canônica para implementação. O histórico git de `62791de` permanece como evidência de origem, não como governança.

---

## 1. Problema

### 1.1 Sintoma (usuário)

> “Estava esperando que já tivesse coisa melhor que o Whisper. Nos vídeos que têm música de fundo ou algum barulho/vozes, o resultado fica muito ruim.”

### 1.2 Causa técnica (baseline)

Pipeline em `core/audio.py` só entrega WAV `pcm_s16le` **16 kHz mono**. Não há denoise, loudnorm, EQ de fala nem proveniência de preprocess. Whisper recebe o sinal bruto pós-conversão.

### 1.3 Expectativa honesta de produto

| Cenário | Expectativa com FFmpeg filters |
|---------|--------------------------------|
| Ruído leve / volume baixo | Melhora significativa |
| Música de fundo moderada | Melhora moderada |
| Música alta / show / vozes sobrepostas | Continua difícil; recomenda-se **modelo medium/large** (orientação UI/README, **sem** troca automática de modelo) |
| Separação de fontes | **Fora de v1** (Demucs/UVR) |

Mensagem: *melhoramos o sinal de entrada; o teto ainda é o modelo ASR*. Filtros **não** separam música nem falantes.

---

## 2. Objetivo v1

1. Pré-processamento FFmpeg opcional **antes** do Whisper e **antes** do `audio_hash` pós-processamento.
2. Presets: `off` | `light` | `speech` (default **`off`** — regressão segura).
3. Um único ponto de aplicação no worker (streaming, traditional, keep_video extract, local file).
4. Snapshot do preset **congelado por job/batch** (não reler Settings a cada item).
5. Proveniência: `source_audio_hash`, `audio_hash`, preset solicitado/aplicado, assinatura do filter graph.
6. Testes unitários + smoke FFmpeg + QA com gate WER.
7. Orientação medium+ e limitações no README/tooltip.

---

## 3. Não-objetivos (v1)

- VAD / Silero
- Source separation (Demucs, MDX, UVR)
- Troca de motor ASR (faster-whisper, WhisperX)
- Diarização
- Fine-tune
- `silenceremove` (proibido — corta silêncios e quebra timestamps/chunks)
- Reprocessamento automático da biblioteca antiga
- Troca automática de modelo Whisper

---

## 4. Decisões Codex / invariantes de implementação

### 4.1 API de resultado

```python
@dataclass(frozen=True)
class AudioPreprocessResult:
    path: str                      # WAV efetivo para Whisper
    requested_preset: str          # off|light|speech (normalizado)
    applied_preset: str            # o que de fato rodou (pode ser fallback)
    filter_graph: str | None       # assinatura do -af usado, ou None se off
    fallback_reason: str | None    # motivo se applied != requested
    source_audio_hash: str         # hash do WAV antes do preprocess
    audio_hash: str                # hash do WAV após preprocess (igual se off)
```

### 4.2 Presets FFmpeg (canônicos)

| Preset | Filter graph | Notas |
|--------|--------------|-------|
| `off` | — | **Não** chama FFmpeg; retorna o mesmo path; bytes inalterados; hashes iguais |
| `light` | `highpass=f=80,lowpass=f=7600,loudnorm=I=-16:TP=-1.5:LRA=11` | Seguro, barato |
| `speech` | `highpass=f=100,lowpass=f=7000,afftdn=nr=12:nf=-25,dynaudnorm=f=150:g=15` | Agressivo; fallback se falhar |

Sempre reencode final: `-acodec pcm_s16le -ar 16000 -ac 1`.

**Proibido em v1:** `silenceremove`, graphs que encurtem duração de forma intencional, empilhar light+speech.

### 4.3 Atomicidade e validação

1. Escrever em temporário **no mesmo diretório** do WAV de trabalho (ex.: `stem.asrprep.tmp.wav`).
2. Validar output: arquivo existe, abre com `wave`, `sampwidth==2`, `nchannels==1`, `framerate==16000`, frames > 0.
3. Só então `os.replace(tmp, work_wav)` (substitui o WAV de trabalho).
4. Em falha / cancelamento / validação inválida: remover tmp; manter original.
5. Fallback em cadeia: `speech` → tenta `light` → se `light` falhar, mantém original (`applied_preset=off` ou path original com reason).

### 4.4 Proveniência e hash

- `source_audio_hash` = SHA-256 do WAV **antes** do preprocess.
- `audio_hash` = SHA-256 do WAV **enviado ao Whisper** (pós-preprocess).
- Com `off`: iguais; sem FFmpeg.
- Persistidos em `transcriptions` sem quebrar DBs legados (`_ensure_column`).

Campos novos sugeridos:

| Coluna | Tipo |
|--------|------|
| `source_audio_hash` | TEXT |
| `asr_preprocess_requested` | TEXT |
| `asr_preprocess_applied` | TEXT |
| `asr_preprocess_filter` | TEXT |
| `asr_preprocess_fallback_reason` | TEXT |

(`audio_hash` já existe.)

### 4.5 Freeze do preset por job

- Setting global: `asr_audio_preprocess` ∈ {off, light, speech}, default `off`.
- Valor legado inválido → normalizar para `off` + warning.
- Em `create_job` / `create_batch_job`: copiar preset atual para payload/snapshot do job.
- Jobs legados sem snapshot → migrar para `off`.
- Todos os itens de um batch usam o **mesmo** snapshot (não reconsultam Settings no meio).

### 4.6 Worker — ponto único

```text
download/extract/convert → WAV de trabalho (16k mono)
  → source_audio_hash = hash(WAV)
  → AudioProcessor.preprocess_for_asr(WAV, preset_snapshot)
  → audio_hash = hash(WAV efetivo)   # ou do result
  → dedup / Whisper / save_transcription(+proveniência)
```

Aplicar **uma vez** por item, nos quatro caminhos:

1. Streaming
2. Traditional audio download
3. keep_video extract
4. Arquivo local

Nunca modificar: arquivo local de entrada, vídeo baixado, archive HQ. Só o WAV de trabalho.
`keep_audio=1` preserva o WAV **efetivamente transcrito** (pós-preprocess).

Progresso: estágio `audio_preprocess` (+ log de fallback).

### 4.7 UI / docs

- Combobox Settings: Desligado / Leve / Fala → off / light / speech.
- Tooltip e README: medium/large para áudio sujo; filtros não separam música/vozes; default off.

### 4.8 Gate de qualidade (QA-003)

Benchmark com `jfk.wav` (whisper.cpp samples) + referência versionada:

- Casos: clean, ruído estacionário, fundo tonal/rítmico (gerados em temp).
- WER off/light/speech, mesmo modelo e decode.
- **Aprovar só se:** regressão WER no clean ≤ **5 pp** **e** mediana do melhor preset melhora vs off nos degradados.
- Caso contrário: QA **rejeita** e abre `issue.report` — não afirmar ganho.

---

## 5. API de código proposta

```python
# core/audio.py

ASR_PREPROCESS_PRESETS = {
    "off": None,
    "light": "highpass=f=80,lowpass=f=7600,loudnorm=I=-16:TP=-1.5:LRA=11",
    "speech": "highpass=f=100,lowpass=f=7000,afftdn=nr=12:nf=-25,dynaudnorm=f=150:g=15",
}

VALID_ASR_PRESETS = frozenset(ASR_PREPROCESS_PRESETS)

def normalize_asr_preprocess_preset(value: str | None) -> str:
    """Invalid/legacy → 'off'."""

class AudioProcessor:
    def preprocess_for_asr(
        self,
        audio_path: str,
        preset: str = "off",
        *,
        cancel_check=None,
    ) -> AudioPreprocessResult:
        """
        off: same path, no FFmpeg, hashes equal.
        light/speech: atomic temp → validate → os.replace; fallback chain.
        Never raises for filter failure; degrades gracefully.
        """
```

---

## 6. Tarefas ESAA (já criadas — registro canônico)

Governança: `python -m esaa --root ~/desenvolvimento/down-youtube`

### 6.1 Comandos task create (registro; já aplicados pelo Codex)

```bash
python -m esaa --root . --runner codex task create YT-ASR-PREPROCESS-000 \
  --kind spec \
  --title "Revisar retrospectivamente o plano de pré-processamento ASR" \
  --depends-on "" \
  --output docs/plans/PLAN-asr-audio-preprocess.md

python -m esaa --root . --runner codex task create YT-ASR-PREPROCESS-001 \
  --kind impl \
  --title "Pré-processamento FFmpeg atômico e proveniência ASR" \
  --depends-on YT-ASR-PREPROCESS-000 \
  --output core/audio.py

python -m esaa --root . --runner codex task create YT-ASR-PREPROCESS-002 \
  --kind impl \
  --title "Integrar presets ASR em worker, jobs e Settings" \
  --depends-on YT-ASR-PREPROCESS-001

python -m esaa --root . --runner codex task create YT-ASR-PREPROCESS-003 \
  --kind qa \
  --title "QA funcional e benchmark dos presets ASR" \
  --depends-on YT-ASR-PREPROCESS-001,YT-ASR-PREPROCESS-002
```

(Payloads completos com `boundary_grant`, `acceptance_criteria` e `outputs` estão no event store seq 461/464/467/470.)

### 6.2 Tabela

| ID | Kind | Depends | Outputs principais | Review mode |
|----|------|---------|-------------------|-------------|
| **YT-ASR-PREPROCESS-000** | spec | — | `docs/plans/PLAN-asr-audio-preprocess.md` | docs |
| **YT-ASR-PREPROCESS-001** | impl | 000 | `core/audio.py`, `database.py`, `tests/test_audio_preprocess.py`, `tests/test_get_transcription.py` | functional |
| **YT-ASR-PREPROCESS-002** | impl | 001 | `core/worker.py`, `config.py`, `gui/tabs/settings_tab.py`, `app/jobs.py`, `app/models.py`, `database.py`, testes app, `README.md` | functional |
| **YT-ASR-PREPROCESS-003** | qa | 001, 002 | `tests/asr_preprocess_benchmark.py`, `tests/fixtures/jfk-reference.txt`, `docs/qa/YT-ASR-PREPROCESS-QA-001.md` | regression |

### 6.3 Acceptance criteria (resumo)

**000**

1. Plano marca registro **retrospectivo**; não atribui `62791de` ao ESAA.
2. v1: off/light/speech, medium+, proveniência, testes/QA; VAD/separation/motor fora.
3. Contém create commands, deps, boundaries, ACs, ordem claim/complete/review/verify.

**001**

1. `off` = mesmo path, sem FFmpeg, bytes iguais, hashes iguais.
2. `light`/`speech` graphs canônicos; PCM s16le 16 kHz mono válido.
3. Temp + `os.replace` pós-validação; limpeza em sucesso/falha/cancel.
4. Fallback speech→light→original; result com requested/applied/reason.
5. Colunas de proveniência migradas sem quebrar DB legado.
6. Testes unitários + smoke FFmpeg local, sem rede.

**002**

1. Default `off`; UI Desligado/Leve/Fala; legado inválido → off + warning.
2. Snapshot por job/batch; legado → off; batch uniforme.
3. Quatro caminhos, preprocess 1× antes do hash e Whisper.
4. keep_audio = WAV efetivo; inputs originais intocados; sem tmp residual.
5. Stage `audio_preprocess` + fallback visível.
6. README/tooltip honestos (medium+, sem milagre).
7. Testes setting/snapshot/caminhos/hash/limpeza.

**003**

1. Matriz independente (presets, inválido, fallback, corrupt, cancel, Unicode, hashes).
2. Matriz worker 4 caminhos + keep_audio + batch snapshot.
3. Smoke FFmpeg real: formato, duração, sem temps.
4. Benchmark jfk + degradados + WER.
5. Gate WER: clean ≤5 pp regressão; mediana degradados melhora; senão reject+issue.
6. pytest, compileall, pip check, git diff --check, esaa verify + relatório.

### 6.4 Ordem claim / complete / review / verify

```text
claim 000 (agent-spec) → complete 000 + file_updates plan → review 000 approve (agent-qa, docs)
claim 001 (agent-impl) → implement → complete 001 + file_updates → review 001 approve (functional)
claim 002 (agent-impl) → implement → complete 002 + file_updates → review 002 approve (functional)
claim 003 (agent-qa)  → QA/benchmark → complete 003 + file_updates report → review 003 approve (regression)
python -m esaa --root . verify   # após cada escrita governada
```

Two-step obrigatório: **nunca** colapsar claim+complete na mesma invocação.

Runner: `--runner human-terminal` (ou o runner real da sessão). Actors: `agent-spec` | `agent-impl` | `agent-qa`.

---

## 7. Arquivos impactados

| Arquivo | Task | Mudança |
|---------|------|---------|
| `docs/plans/PLAN-asr-audio-preprocess.md` | 000 | Spec canônica (este doc) |
| `core/audio.py` | 001 | `AudioPreprocessResult`, presets, `preprocess_for_asr` |
| `database.py` | 001/002 | Colunas proveniência; opcional snapshot job |
| `tests/test_audio_preprocess.py` | 001 | Unit + mock FFmpeg + smoke |
| `tests/test_get_transcription.py` | 001 | SELECT/colunas novas |
| `core/worker.py` | 002 | 1× preprocess + progresso + save proveniência |
| `config.py` | 002 | `asr_audio_preprocess=off` |
| `gui/tabs/settings_tab.py` | 002 | Combobox + tooltip |
| `app/jobs.py`, `app/models.py` | 002 | Snapshot preset |
| `README.md` | 002 | Seção ASR preprocess |
| `tests/test_audio_quality.py`, `test_app_jobs.py`, `test_app_worker_bridge.py` | 002 | Regressões |
| `tests/asr_preprocess_benchmark.py` | 003 | WER bench |
| `tests/fixtures/jfk-reference.txt` | 003 | Referência |
| `docs/qa/YT-ASR-PREPROCESS-QA-001.md` | 003 | Relatório QA |

---

## 8. Riscos

| Risco | Mitigação |
|-------|-----------|
| FFmpeg antigo sem `afftdn`/`loudnorm` | Fallback em cadeia |
| Tempo extra | Default `off` |
| Hash muda com preset | Documentar; hash pós-preprocess + source hash |
| Expectativa de milagre | Copy honesta; medium+ |
| silenceremove quebra timestamps | **Proibido** |
| Settings mudam mid-batch | Snapshot no job create |

---

## 9. Roadmap futuro (fora de v1)

| ID | Ideia |
|----|-------|
| YT-ASR-VAD-001 | VAD / só trechos com fala |
| YT-ASR-VOCAL-001 | Demucs/UVR opcional |
| YT-ASR-MODEL-001 | UX mais forte para medium/large |
| YT-ASR-ENGINE-001 | Backend alternativo |

---

## 10. Mensagem ao usuário final

> O Whisper ainda sofre com música e fala misturadas. O app passou a oferecer pré-processamento opcional (filtros FFmpeg: desligado / leve / fala). Recomendamos modelo **medium** ou **large** para áudio sujo. Isso melhora ruído e volume em muitos casos, mas **não** separa trilhas musicais altas nem vozes sobrepostas.

---

## 11. Checklist de aceite do plano (000)

- [x] Aviso retrospectivo: `62791de` **não** foi criado pelo ESAA
- [x] v1: off/light/speech, medium+, proveniência, atomicidade, freeze job, WER gate
- [x] Fora: VAD, separation, troca de motor, silenceremove
- [x] Tasks 000–003 com deps, boundaries, ACs, outputs
- [x] Ordem claim/complete/review/verify documentada
- [x] Default `off`; um ponto no worker; testes + README

---

**Fim da spec canônica.** Pronto para `complete` de `YT-ASR-PREPROCESS-000` e implementação de 001–003.
