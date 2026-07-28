# PLAN: Pré-processamento de áudio para ASR (Whisper)

> **Destino canônico no repo (após aprovação / para o Codex):**  
> `docs/plans/PLAN-asr-audio-preprocess.md`  
> **Workspace:** `~/desenvolvimento/down-youtube`  
> **Data:** 2026-07-28  
> **Motivo:** feedback de usuário — Whisper ruim com música de fundo / barulho / vozes misturadas.  
> **Escopo v1:** filtros FFmpeg + settings + testes. **Fora de v1:** Demucs/UVR, troca de motor ASR.

---

## 1. Problema

### 1.1 Sintoma (usuário)

> “Estava esperando que já tivesse coisa melhor que o Whisper. Nos vídeos que têm música de fundo ou algum barulho/vozes, o resultado fica muito ruim.”

### 1.2 Causa técnica (estado atual)

Pipeline de áudio em `core/audio.py`:

| Etapa | O que faz | O que **não** faz |
|-------|-----------|-------------------|
| `extract_audio` | WAV `pcm_s16le`, **16 kHz**, **mono** | denoise, EQ, loudnorm |
| `normalize_audio` | Reamostra de novo para 16 kHz mono | **Não** é normalização de loudness |
| `convert_to_wav` | Idem 16 kHz mono | filtros de fala |
| Streaming | FFmpeg pipe → 16 kHz mono | mesma limitação |

Whisper (whisper.cpp) recebe sinal **não tratado** para cenários de trilha + fala.

### 1.3 Expectativa honesta (produto)

| Cenário | Expectativa com pré-processamento FFmpeg |
|---------|------------------------------------------|
| Ruído leve / volume baixo | Melhora **significativa** |
| Música de fundo moderada | Melhora **moderada** |
| Música alta / show / várias vozes | Continua difícil; precisa modelo maior e/ou source separation (v2+) |

**Não prometer** “melhor que Whisper em qualquer vídeo”. Mensagem: *melhoramos o sinal de entrada; o teto ainda é o modelo ASR*.

---

## 2. Objetivo

1. Adicionar **pré-processamento de áudio opcional** (FFmpeg filters) **antes** do Whisper.
2. Expor presets na **Settings** e defaults seguros (`off` ou `light`).
3. Aplicar em **todos** os caminhos: streaming, traditional, keep_video extract, local file, batch jobs.
4. Testes unitários determinísticos (mock FFmpeg ou assert da command line).
5. Documentar no README + nota para o usuário final (limitations).

---

## 3. Não-objetivos (v1)

- Separação de fontes (Demucs, MDX, UVR)
- Troca de whisper.cpp por Faster-Whisper / WhisperX
- Diarização de falantes
- Treino / fine-tune de modelo
- Reprocessar automaticamente biblioteca antiga (só novos jobs; reprocess manual)

---

## 4. Desenho da solução

### 4.1 Novo estágio no pipeline

```text
download/extract → WAV bruto (16k mono)
                 → [NOVO] preprocess_for_asr(wav)  // se preset != off
                 → Whisper (chunk se >60min)
```

Ponto único de aplicação (evitar divergência GUI/CLI/API):

- Preferência: método em `AudioProcessor` chamado no `TranscriberWorker` **uma vez** quando o WAV final estiver pronto, **antes** de `audio_hash` / `_run_transcription`.
- Alternativa aceitável: aplicar dentro de `normalize_audio` se o preset estiver ativo (renomear semanticamente).

**Importante:** `audio_hash` deve ser calculado **depois** do preprocess (hash do áudio efetivamente transcrito), ou documentar se hash permanece do original. Recomendação: **hash do áudio enviado ao Whisper** (pós-preprocess).

### 4.2 Presets FFmpeg (v1)

Setting: `asr_audio_preprocess` ∈ {`off`, `light`, `speech`}

| Preset | Filter graph (proposta) | Notas |
|--------|-------------------------|--------|
| `off` | (nenhum extra) | Default atual / comportamento legado |
| `light` | `highpass=f=80,lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11` | Seguro, barato |
| `speech` | `highpass=f=100,lowpass=f=7000,afftdn=nr=12:nf=-25,dynaudnorm=f=150:g=15` | Mais agressivo; se `afftdn` falhar no FFmpeg do user, fallback para `light` |

Implementação: montar `-af "..."` no FFmpeg; **um** pass de saída `pcm_s16le` 16 kHz mono.

**Fallback:** se FFmpeg retornar erro no graph `speech`, logar warning e tentar `light`; se `light` falhar, manter WAV original e seguir (não falhar o job só por preprocess).

### 4.3 Settings / config

| Key | Default | UI |
|-----|---------|-----|
| `asr_audio_preprocess` | `off` | Combobox: Desligado / Leve / Fala (speech) |
| (opcional v1.1) `asr_audio_preprocess_keep_raw` | `0` | Manter `.raw.wav` ao lado do processado |

Arquivos:

- `config.py` — `DEFAULT_SETTINGS`
- `gui/tabs/settings_tab.py` — combobox + tooltip honesto
- `core/worker.py` — ler setting e chamar preprocess
- `core/audio.py` — `preprocess_for_asr(path, preset, ...)`
- `core/streaming_downloader.py` — se o WAV já sai do pipe, preprocess **após** materializar o arquivo (não no pipe v1, para simplicidade)

### 4.4 API / CLI

Sem endpoints novos no v1: herdam o setting do app DB (mesmo `settings` SQLite).

Opcional: `python -m cli` não precisa flag se setting global bastar. Flag futura: `--asr-preprocess speech`.

### 4.5 App layer / jobs

Jobs usam `TranscriberWorker` → sem mudança de contrato de job; só comportamento interno do worker.

---

## 5. API de código proposta

```python
# core/audio.py

PRESETS = {
    "off": None,
    "light": "highpass=f=80,lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11",
    "speech": "highpass=f=100,lowpass=f=7000,afftdn=nr=12:nf=-25,dynaudnorm=f=150:g=15",
}

class AudioProcessor:
    def preprocess_for_asr(
        self,
        audio_path: str,
        output_dir: str,
        preset: str = "off",
    ) -> str:
        """
        Return path to WAV ready for Whisper.
        On failure: log + return original audio_path.
        Always ensure 16k mono pcm_s16le.
        """
```

Worker (pseudocódigo):

```python
arquivo_wav = ...  # download/extract
preset = cfg.get("asr_audio_preprocess") or "off"
arquivo_wav = audio_processor.preprocess_for_asr(arquivo_wav, output_dir, preset)
# then hash + transcribe
```

---

## 6. Tarefas ESAA sugeridas

Governança: `esaa --root ~/desenvolvimento/down-youtube`

| ID | Kind | Título | Depends |
|----|------|--------|---------|
| **YT-ASR-PREPROCESS-000** | `spec` | Spec/plan preprocess áudio ASR (este doc em `docs/plans/`) | — |
| **YT-ASR-PREPROCESS-001** | `impl` | `AudioProcessor.preprocess_for_asr` + presets FFmpeg + fallback | 000 |
| **YT-ASR-PREPROCESS-002** | `impl` | Wire worker (todos os caminhos) + setting default + Settings UI | 001 |
| **YT-ASR-PREPROCESS-003** | `impl` | Testes + README + limitações + tooltip Settings | 002 |

### 6.1 YT-ASR-PREPROCESS-001 — ACs

1. `preprocess_for_asr(..., "off")` retorna path original (ou reencode mínimo idêntico em formato).
2. Preset `light` e `speech` geram WAV 16 kHz mono (assert command contém `-af` e `-ar 16000`).
3. Falha de FFmpeg no preset agressivo faz fallback sem levantar exceção não tratada.
4. Testes unitários sem rede; FFmpeg mockado via monkeypatch de `subprocess.run`.

### 6.2 YT-ASR-PREPROCESS-002 — ACs

1. Setting `asr_audio_preprocess` em `DEFAULT_SETTINGS` e Settings UI.
2. Worker aplica preprocess antes da transcrição nos caminhos: streaming, traditional audio, keep_video extract, local file.
3. Com preset `off`, comportamento regressivo (hash/transcrição como hoje em mocks).
4. Tooltip/UI **não** promete milagre com música alta.

### 6.3 YT-ASR-PREPROCESS-003 — ACs

1. `tests/test_audio_preprocess.py` cobre off/light/speech/fallback.
2. README: seção curta “ASR audio preprocess” + limitações.
3. `pytest` suite relevante passa.

---

## 7. Arquivos impactados

| Arquivo | Mudança |
|---------|---------|
| `docs/plans/PLAN-asr-audio-preprocess.md` | Este plano (cópia canônica) |
| `core/audio.py` | `preprocess_for_asr`, presets |
| `core/worker.py` | chamar preprocess pós-WAV |
| `config.py` | default setting |
| `gui/tabs/settings_tab.py` | combobox + save/load |
| `tests/test_audio_preprocess.py` | novo |
| `README.md` | docs |

Opcional: `core/streaming_downloader.py` só se o WAV for finalizado sem passar pelo worker path comum — preferir **um** call no worker.

---

## 8. Testes (mínimo adversário)

| Teste | Intenção |
|-------|----------|
| `off` não adiciona `-af` | regressão |
| `light` inclui highpass/loudnorm na cmdline | contrato preset |
| `speech` fallback quando returncode≠0 | robustez |
| worker com preset mockado chama preprocess 1x | wiring |
| output sempre `-ar 16000 -ac 1` | contrato Whisper |

Não exigir FFmpeg real no CI se ambiente não tiver; mock `subprocess.run`.

---

## 9. Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| `loudnorm` / `afftdn` indisponível em FFmpeg antigo | fallback em cadeia; detectar erro e degradar |
| Preprocess aumenta tempo | default `off`; `light` aceitável |
| Hash de áudio muda com preset | documentar; hash pós-preprocess |
| Usuário espera milagre | copy/tooltip honestos |
| Double-normalize (loudnorm + dynaudnorm) | presets disjuntos, não empilhar todos |

---

## 10. Roadmap futuro (fora deste plano)

| ID futuro | Ideia |
|-----------|--------|
| YT-ASR-VAD-001 | Silero/VAD — só trechos com fala |
| YT-ASR-VOCAL-001 | Demucs/UVR opcional (GPU) |
| YT-ASR-MODEL-001 | Recomendar medium/large na UI para áudio sujo |
| YT-ASR-ENGINE-001 | Backend alternativo (faster-whisper) |

---

## 11. Critérios de aceite do plano (para Codex / implementador)

- [ ] Plano copiado para `docs/plans/PLAN-asr-audio-preprocess.md`
- [ ] Tasks ESAA criadas (000–003) **antes** de código, se governança strict
- [ ] Default não quebra usuários atuais (`off`)
- [ ] Um único ponto de preprocess no worker
- [ ] Testes + README
- [ ] Sem dependência nova pesada no v1 (só FFmpeg já exigido)

---

## 12. Mensagem sugerida (resposta ao usuário final)

> O Whisper ainda sofre com música e fala misturadas. O app hoje só prepara o áudio em 16 kHz mono. Vamos adicionar pré-processamento opcional (filtros FFmpeg) e recomendar modelo maior para áudio sujo. Não elimina 100% o problema em trilhas altas, mas melhora casos comuns de ruído e volume.

---

## 13. Ordem de execução recomendada (Codex)

1. Salvar este arquivo em `docs/plans/PLAN-asr-audio-preprocess.md`
2. `esaa task create YT-ASR-PREPROCESS-000` (spec) com output no plan path — ou pular se o plano já for a spec
3. Implementar 001 → 002 → 003 (claim/complete/review separados)
4. `pytest` + `esaa verify`
5. Commit/push sob pedido do usuário

---

## 14. Referências de código atual

- `core/audio.py` — extract/normalize/convert (sem filtros ASR)
- `core/worker.py` — após download/extract chama normalize; ponto de inserção
- `core/streaming_downloader.py` — pipe FFmpeg 16 kHz mono
- `core/transcriber.py` — whisper-cli; chunk >60 min
- `config.py` — `DEFAULT_SETTINGS`
- `gui/tabs/settings_tab.py` — padrões de UI de opções

---

**Fim do plano.** Pronto para análise e implementação pelo Codex sob ESAA.
