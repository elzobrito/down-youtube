# 🎬 YouTube Transcriber

Aplicativo desktop para baixar vídeos do YouTube, transcrever com **whisper.cpp** e gerenciar transcrições. Inclui **streaming pipeline**, tema dark, modo NERD com métricas detalhadas e notificações Windows.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)

---

## ✨ Funcionalidades

| Categoria | Features |
|-----------|----------|
| **🚀 Download** | Streaming pipeline (30% mais rápido), cookies bypass, auto-detect yt-dlp |
| **🗣️ Transcrição** | whisper.cpp, GPU/CPU, configurável (threads, beam size, best of) |
| **📚 Organização** | Fila persistente, Biblioteca com busca, Histórico com reprocessamento |
| **🎨 Interface** | Tema Dark customizado, Modo NERD, Notificações Windows Toast |

---

## 📋 Pré-requisitos

### 1. Python 3.8+
```bash
python --version  # 3.8+
```

### 2. FFmpeg
```bash
# Windows: baixe de https://www.gyan.dev/ffmpeg/builds/
# Adicione ao PATH ou configure caminho no app

ffmpeg -version  # verificar
```

### 3. whisper.cpp
```bash
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build && cmake --build build --config Release
./models/download-ggml-model.sh base
```

### 4. yt-dlp
```bash
pip install yt-dlp  # recomendado
```

---

## 🚀 Instalação

```bash
git clone https://github.com/seu-usuario/youtube-transcriber.git
cd youtube-transcriber
pip install -r requirements.txt
python main.py
```

---

## ⚙️ Configuração Recomendada

### Para Intel i7 (4 cores):
| Parâmetro | Valor | Razão |
|-----------|-------|-------|
| Threads | 4 | 1 por core físico |
| Beam size | 5 | Equilíbrio qualidade/velocidade |
| Best of | 1 | Padrão |
| GPU CUDA | ❌ | Só se compilou com CUDA |

### Caminhos necessários:
- **FFmpeg**: `C:\FFMPEG\bin\ffmpeg.exe`
- **Whisper CLI**: `C:\whisper.cpp\build\bin\Release\whisper-cli.exe`
- **Modelo**: `C:\whisper.cpp\models\ggml-base.bin`
- **Saída**: `D:\transcricoes`

---

## 🎨 Interface

### Abas
| Aba | Função |
|-----|--------|
| **Download** | URL única, arquivo local, progresso em tempo real |
| **Fila** | Lista persistente, processar em lote |
| **Biblioteca** | Busca, exportação (TXT, SRT, VTT, DOCX, PDF) |
| **Histórico** | Reprocessamento, status de cada item |
| **Configurações** | Paths, performance, tema, notificações |

### 🔍 Modo NERD

Painel expansível com métricas técnicas detalhadas:

```
📊 Download Stats
  • yt-dlp version: 2025.12.08
  • Format: bestaudio (m4a, 128kbps)
  • Cookies: ✅ Loaded

🎵 Conversion Stats
  • FFmpeg: -ar 16000 -ac 1 -c:a pcm_s16le
  • Sample rate: 48kHz → 16kHz

🗣️ Transcription Stats
  • Model: ggml-base.bin
  • Backend: whisper.cpp
  • Speed: 0.85x realtime
```

### 🌙 Tema Dark

Configurações → Tema → **Dark (Custom)**

- Inspirado no VS Code Dark+
- Aplicado a todos os widgets
- Área de log escura

---

## 🚀 Streaming Pipeline

Download e conversão **paralelos**, economizando 25-35% de tempo:

```
Tradicional:  Download ━━━━━ 30s → Conversão ━━ 10s  = 40s
Streaming:    Download ━━━━━ 30s
              Conversão  ━━━━ 10s (paralelo!)        = 30s ✨
```

Ativar: Configurações → **Pipeline de Streaming** → Salvar

---

## 🍪 Cookies do YouTube

### Quando preciso?

Se aparecer:
```
ERROR: Sign in to confirm you're not a bot
```

### Como exportar (Edge):

1. Instalar [Get cookies.txt LOCALLY](https://microsoftedge.microsoft.com/addons/detail/pdabbpcmapcjfjpkdhpbhcmbflgpjjfp)
2. Abrir youtube.com (logado)
3. Extensão → Export
4. Configurações → Cookies → Selecionar arquivo

> ⚠️ Cookies expiram em ~1-2 semanas

---

## 🔔 Notificações

Windows Toast ao finalizar processamento.

**Requisito:**
```bash
pip install winotify
```

**Testar:** Configurações → Notificações → **Testar**

---

## 🔧 Troubleshooting

| Problema | Solução |
|----------|---------|
| `yt-dlp não encontrado` | `pip install yt-dlp` |
| `Sign in to confirm you're not a bot` | Exportar cookies do YouTube |
| `HTTP Error 403` | Usar cookies ou VPN |
| `FFmpeg não encontrado` | Configurar path correto |
| `GPU não funciona` | Recompilar whisper.cpp com CUDA ou desmarcar |
| `Notificação não aparece` | `pip install winotify`, testar no app |
| `NERD panel cortado` | Atualizado! Agora tem scrollbar |

---

## 📁 Estrutura

```
youtube-transcriber/
├── main.py                    # Entry point
├── gui/
│   ├── app.py                # Main window
│   ├── tabs/                 # Download, Fila, Biblioteca, Histórico, Config
│   ├── widgets/              # StageProgress, NerdPanel, StatsPanel
│   └── themes/dark_custom.py # Tema dark
├── core/
│   ├── worker.py             # Orquestração
│   ├── streaming_downloader.py # Pipeline paralelo
│   ├── audio_processor.py    # Conversão WAV
│   └── transcriber.py        # whisper.cpp
├── integrations/
│   └── notifications.py      # Windows Toast
└── database.py               # SQLite
```

---

## 📈 Changelog

### v2.1 (2026-01)
- 🎨 **Tema Dark** customizado (VS Code-inspired)
- 🔍 **Modo NERD** com métricas técnicas detalhadas
- 🔔 **Notificações** Windows Toast com botão de teste
- 📊 **Barra de conversão** funcional
- ⚡ **Estatísticas** dinâmicas (velocidade realtime)

### v2.0
- 🚀 Streaming Pipeline (25-35% mais rápido)
- 🍪 Suporte a Cookies
- 🔍 Auto-detecção yt-dlp

---

## 📄 Licença

MIT

---

**Feito com ❤️ para transcrição de vídeos**
