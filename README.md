# 🎬 YouTube Transcriber

Aplicativo com interface grafica para baixar audio, transcrever com **whisper.cpp** e armazenar tudo no SQLite. Inclui fila persistente, biblioteca de transcricoes, historico com reprocessamento e suporte a arquivos locais.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

## ✨ Funcionalidades

- **Download otimizado** com yt-dlp (audio ou video + extracao)
- **Transcricao automatica** via whisper.cpp (modelo definido pelo usuario)
- **Fila persistente** no SQLite (pending/processing/done/failed)
- **Biblioteca** com busca e exportacao (TXT, SRT, VTT, DOCX, PDF)
- **Historico** com reprocessamento e abertura de midia
- **Arquivo local** (video ou audio) com conversao para WAV 16k mono
- **Modo portatil** com data/ local

## 📋 Pre-requisitos

### 1. Python 3.8+

Baixe em [python.org](https://www.python.org/downloads/)

### 2. FFmpeg

**Windows:**
1. Baixe em [ffmpeg.org](https://ffmpeg.org/download.html) ou [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
2. Extraia para `C:\FFMPEG`
3. Adicione `C:\FFMPEG\bin` ao PATH

**Linux:**
```bash
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 3. whisper.cpp (v1.8.3)

Clone e compile o whisper.cpp:

```bash
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j --config Release
```

Baixe um modelo:

```bash
./models/download-ggml-model.sh base
```

**CUDA (opcional):**

```bash
cmake -B build -DGGML_CUDA=1
cmake --build build -j --config Release
```

## 🚀 Instalacao

```bash
git clone https://github.com/seu-usuario/youtube-transcriber.git
cd youtube-transcriber
pip install -r requirements.txt
```

## ▶️ Executar

```bash
python main.py
```

Ou:

```bash
python youtube_transcriber.py
```

## ⚙️ Configuracao

Abra a aba **Configuracoes** e ajuste:

- **FFmpeg**: caminho do executavel
- **Whisper CLI**: caminho do `whisper-cli`
- **Modelo Whisper**: arquivo `.bin`
- **Idioma**: ex. `portuguese`
- **Threads**: 0 = auto
- **Beam size / Best of**
- **Manter audio** (opcional)
- **Manter video** (opcional, usa MP4)

Observacao: GPU so funciona com whisper-cli compilado com CUDA. Caso contrario, o app usa CPU normalmente.

## 📖 Como usar

### URL (YouTube)

1. Cole a URL na aba **Download**
2. Clique em **Processar**
3. A transcricao aparece na **Biblioteca** e no **Historico**

### Arquivo local

1. Clique em **Arquivo local**
2. Selecione um video ou audio
3. O app converte para WAV 16k mono e transcreve

### Fila persistente

- Itens da fila ficam salvos no SQLite
- **Processar Fila** executa apenas `pending` e `failed`
- Itens processados ficam como `done`

## 📁 Banco de dados

O SQLite fica em:

- **Normal:** `%USERPROFILE%/.youtube_transcriber/youtube_transcriber.db`
- **Portatil:** `./data/youtube_transcriber.db` (crie `portable.flag` na raiz)

## 📦 Estrutura de saida

- `.txt` da transcricao no diretorio de saida
- Audio e video sao removidos por padrao, a menos que voce marque as opcoes

## 🔧 Solucao de problemas

### Erro: unknown argument

Sua versao do `whisper-cli` pode nao aceitar certas flags.
Exemplo: use `-bs/--beam-size` em vez de `-b`.

### whisper-cli nao encontrado

Configure o caminho correto na aba **Configuracoes** ou adicione ao PATH.

### ffmpeg nao encontrado

Instale o FFmpeg e configure o caminho no app.

### GPU nao funciona

O whisper.cpp precisa ser compilado com CUDA (`GGML_CUDA=1`). Sem isso, o app roda em CPU.

## 🤝 Contribuindo

1. Fork do projeto
2. Crie uma branch (`git checkout -b feature/nova-funcionalidade`)
3. Commit (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push (`git push origin feature/nova-funcionalidade`)
5. Abra um Pull Request

## 📄 Licenca

MIT

## 🙏 Agradecimentos

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
- [FFmpeg](https://ffmpeg.org/)
