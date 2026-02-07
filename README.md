# YouTube Transcriber

Aplicativo desktop completo para download, transcrição e gerenciamento de vídeos do YouTube. Integra **whisper.cpp** para transcrição local, **Ollama** para chat com IA sobre as transcrições, exportação em múltiplos formatos e uma interface rica com tema dark, tooltips, menus de contexto e modo NERD.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)

---

## Funcionalidades

| Categoria      | Features                                                                                               |
| -------------- | ------------------------------------------------------------------------------------------------------ |
| **Download**   | Streaming pipeline (download + conversão paralelos), cookies bypass, auto-detect yt-dlp, arquivo local |
| **Transcrição** | whisper.cpp com GPU/CPU, configurável (threads, beam size, best of), detecção de duplicatas por hash  |
| **Chat IA**    | Integração com Ollama, sessões persistentes, streaming de respostas, contexto da transcrição           |
| **Exportação** | TXT, SRT, VTT, DOCX, PDF                                                                              |
| **Biblioteca** | Busca full-text, filtro por idioma, preview, flag de uso, acesso a áudio/vídeo originais               |
| **Fila**       | Fila persistente com prioridade, importação de .txt, processamento em lote                             |
| **Histórico**  | Status por item, reprocessamento, acesso a arquivos                                                    |
| **Interface**  | Tema Dark (VS Code-inspired), tooltips, menus de contexto, notificações flash, modo NERD               |

---

## Pré-requisitos

### 1. Python 3.8+

```bash
python --version
```

### 2. FFmpeg

```bash
# Windows: baixe de https://www.gyan.dev/ffmpeg/builds/
# Adicione ao PATH ou configure o caminho no app
ffmpeg -version
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
pip install yt-dlp
```

### 5. Ollama (opcional, para Chat IA)

```bash
# Baixe de https://ollama.com
ollama pull llama3
```

---

## Instalação

```bash
git clone https://github.com/seu-usuario/youtube-transcriber.git
cd youtube-transcriber
pip install -r requirements.txt
python main.py
```

### Dependências

| Pacote           | Uso                         |
| ---------------- | --------------------------- |
| `yt-dlp`         | Download de vídeos          |
| `Pillow`         | Processamento de imagens    |
| `python-docx`    | Exportação DOCX             |
| `reportlab`      | Exportação PDF              |
| `deep-translator` | Tradução                   |
| `winotify`       | Notificações Windows Toast  |
| `ttkthemes`      | Temas avançados para Tkinter |

---

## Interface

A aplicação é organizada em 6 abas:

### Download

Aba principal para processar URLs do YouTube ou arquivos locais.

- Campo de URL com detecção automática da área de transferência
- Progresso em 3 estágios independentes:
  - **Download** - MB baixados, velocidade, ETA
  - **Conversão** - Formato, velocidade, tamanho
  - **Transcrição** - Modelo, threads, tempo decorrido, palavras estimadas
- Painel de estatísticas do sistema (tempo, disco, CPU, threads, ganho do pipeline)
- Badge de pipeline mostrando o modo ativo (Streaming/Tradicional/Vídeo)
- Log aprimorado com timestamps coloridos e botões Salvar/Limpar

**Atalhos:**

| Tecla    | Ação                       |
| -------- | -------------------------- |
| `Enter`  | Processar URL              |
| `Escape` | Cancelar ou limpar campo   |
| `Ctrl+L` | Focar no campo de URL      |

### Fila

Gerenciamento de múltiplas URLs para processamento em lote.

- Adicionar URLs individualmente ou importar de arquivo .txt
- Status por item: pendente, processando, concluído, falhou, pulado
- Menu de contexto: copiar URL, remover item
- Processamento sequencial automático de toda a fila

### Biblioteca

Central de gerenciamento das transcrições concluídas.

- Busca full-text com snippets de preview
- Filtro por idioma (Português, Inglês, Espanhol)
- Painel de preview lateral
- Estatísticas: total de transcrições, palavras e horas
- Flag de uso (marcar transcrição como utilizada)
- Acesso direto ao áudio e vídeo originais
- Chat IA por transcrição (abre janela com Ollama)
- Exportação em 5 formatos (TXT, SRT, VTT, DOCX, PDF)

### Chat IA

Janela de chat integrada com Ollama para interagir com as transcrições.

- Sessões persistentes por transcrição (salvas no banco)
- Injeção automática do texto da transcrição como contexto
- Streaming de respostas em tempo real
- Histórico de conversas com criação/exclusão de sessões
- Indicador de status de conexão com o Ollama

### Histórico

Registro de todos os processamentos realizados.

- Status: OK, Pulado, Erro
- Reprocessamento de itens com falha
- Acesso a arquivos de áudio/vídeo
- Menu de contexto com copiar URL e reprocessar

### Configurações

| Seção           | Opções                                                          |
| --------------- | --------------------------------------------------------------- |
| **Caminhos**    | FFmpeg, Whisper CLI, modelo, diretório de saída, cookies        |
| **Idioma**      | Português, Inglês, Espanhol, Francês, Alemão, Italiano, Auto   |
| **Performance** | Threads (0=auto), beam size, best of, GPU CUDA                  |
| **Opções**      | Manter áudio, manter vídeo, notificações, streaming pipeline    |
| **Tema**        | Temas nativos + Dark Custom                                      |
| **Ollama**      | URL do servidor, nome do modelo                                  |
| **Backup**      | Criar/restaurar backup do banco de dados                         |

---

## Streaming Pipeline

Download e conversão em paralelo, economizando 25-35% de tempo:

```text
Tradicional:  Download ━━━━━ 30s  ->  Conversão ━━ 10s  = 40s
Streaming:    Download ━━━━━ 30s
              Conversão  ━━━━ 10s (paralelo!)            = 30s
```

Ativar em: Configurações > Pipeline de Streaming > Salvar

---

## Modo NERD

Painel expansível com métricas técnicas detalhadas, dividido em 4 seções:

- **Download Stats** - Chunks, bytes, velocidade, progresso
- **Conversion Stats** - Codec, bitrate, informações de frame
- **Transcription Stats** - Palavras/seg, confiança, timing
- **File System** - Velocidade de disco, padrões de I/O

---

## Exportação

| Formato  | Descrição                                     |
| -------- | --------------------------------------------- |
| **TXT**  | Texto puro sem timecodes                      |
| **SRT**  | Legendas com timecodes `HH:MM:SS,mmm`        |
| **VTT**  | WebVTT com timecodes `HH:MM:SS.mmm`          |
| **DOCX** | Documento Word formatado com título           |
| **PDF**  | PDF multi-página com título e parágrafos      |

---

## Cookies do YouTube

Necessário quando aparecer:

```text
ERROR: Sign in to confirm you're not a bot
```

### Como exportar (Edge)

1. Instalar [Get cookies.txt LOCALLY](https://microsoftedge.microsoft.com/addons/detail/pdabbpcmapcjfjpkdhpbhcmbflgpjjfp)
2. Abrir youtube.com (logado)
3. Extensão > Export
4. Configurações > Cookies > Selecionar arquivo

> Cookies expiram em ~1-2 semanas

---

## Configuração Recomendada

### Para Intel i7 (4 cores)

| Parâmetro  | Valor      | Razão                              |
| ---------- | ---------- | ---------------------------------- |
| Threads    | 4          | 1 por core físico                  |
| Beam size  | 5          | Equilíbrio qualidade/velocidade    |
| Best of    | 1          | Padrão                             |
| GPU CUDA   | Desativado | Só se compilou whisper.cpp com CUDA |

### Caminhos padrão

- **FFmpeg**: `C:\FFMPEG\bin\ffmpeg.exe`
- **Whisper CLI**: `C:\whisper.cpp\build\bin\Release\whisper-cli.exe`
- **Modelo**: `C:\whisper.cpp\models\ggml-base.bin`
- **Saída**: `~/Downloads/Transcricoes`

---

## Troubleshooting

| Problema                              | Solução                                                  |
| ------------------------------------- | -------------------------------------------------------- |
| `yt-dlp não encontrado`              | `pip install yt-dlp`                                     |
| `Sign in to confirm you're not a bot` | Exportar cookies do YouTube                              |
| `HTTP Error 403`                      | Usar cookies ou VPN                                      |
| `FFmpeg não encontrado`              | Configurar path correto em Configurações                  |
| `GPU não funciona`                   | Recompilar whisper.cpp com CUDA ou desmarcar a opção      |
| `Notificação não aparece`            | `pip install winotify`, testar no app                     |
| `Ollama não conecta`                 | Verificar se o servidor está rodando (`ollama serve`)     |
| `Chat sem resposta`                   | Verificar modelo configurado e conexão com Ollama         |

---

## Estrutura do Projeto

```text
youtube-transcriber/
├── main.py                         # Entry point
├── database.py                     # SQLite (videos, transcrições, chat, fila, histórico)
├── config.py                       # Configurações e defaults
├── gui/
│   ├── app.py                      # Janela principal e orquestração de abas
│   ├── tabs/
│   │   ├── download_tab.py         # Download e transcrição
│   │   ├── queue_tab.py            # Fila de URLs
│   │   ├── library_tab.py         # Biblioteca de transcrições
│   │   ├── chat_tab.py             # Chat IA com Ollama
│   │   ├── history_tab.py          # Histórico de processamento
│   │   └── settings_tab.py         # Configurações
│   ├── widgets/
│   │   ├── enhanced_log.py         # Log com timestamps e cores
│   │   ├── stage_progress_panel.py # Progresso em 3 estágios
│   │   ├── stats_panel.py          # Estatísticas do sistema
│   │   ├── nerd_panel.py           # Painel NERD (métricas avançadas)
│   │   ├── pipeline_badge.py       # Badge do modo de pipeline
│   │   ├── context_menu.py         # Menus de contexto (clique direito)
│   │   ├── status_flash.py         # Notificações flash temporárias
│   │   ├── tooltip.py              # Tooltips de hover
│   │   ├── video_preview.py        # Preview de vídeo
│   │   ├── search_box.py           # Campo de busca
│   │   └── progress_bar.py         # Barra de progresso customizada
│   └── themes/
│       └── dark_custom.py          # Tema dark (VS Code-inspired)
├── core/
│   ├── worker.py                   # Orquestração e threading
│   ├── downloader.py               # Download via yt-dlp
│   ├── streaming_downloader.py     # Pipeline paralelo (streaming)
│   ├── audio.py                    # Extração e normalização de áudio
│   ├── transcriber.py              # Interface com whisper.cpp
│   ├── exporter.py                 # Exportação (TXT, SRT, VTT, DOCX, PDF)
│   ├── ollama_client.py            # Cliente REST para Ollama
│   ├── translator.py               # Tradução
│   └── updater.py                  # Atualizações
├── integrations/
│   └── notifications.py            # Windows Toast (winotify)
└── utils/
    ├── backup.py                   # Backup/restore do banco
    └── portable.py                 # Modo portátil
```

---

## Banco de Dados

SQLite com as seguintes tabelas:

| Tabela           | Descrição                                                             |
| ---------------- | --------------------------------------------------------------------- |
| `settings`       | Configurações chave-valor                                             |
| `videos`         | Metadados dos vídeos (URL, título, canal, duração, caminhos)         |
| `transcriptions` | Transcrições com texto, segmentos JSON, hash de áudio, flag de uso    |
| `translations`   | Traduções de transcrições                                             |
| `history`        | Histórico de processamento com status e tempo                         |
| `queue`          | Fila de URLs com prioridade e status                                  |
| `chat_sessions`  | Sessões de chat com Ollama por transcrição                            |
| `chat_messages`  | Mensagens individuais de cada sessão (user/assistant)                 |

---

## Changelog

### v3.0 (2026-02)

- Chat IA com Ollama (sessões persistentes, streaming, contexto automático)
- Exportação SRT e VTT com timecodes
- Menus de contexto em toda a aplicação
- Tooltips de hover nos botões
- Notificações flash temporárias (StatusFlash)
- Log aprimorado com timestamps e cores
- Flag de uso nas transcrições (marcar como utilizada)
- Filtro por idioma na Biblioteca
- Acesso direto a áudio/vídeo originais
- Detecção de duplicatas por hash de áudio
- Backup e restore do banco de dados

### v2.1 (2026-01)

- Tema Dark customizado (VS Code-inspired)
- Modo NERD com métricas técnicas detalhadas
- Notificações Windows Toast com botão de teste
- Barra de conversão funcional
- Estatísticas dinâmicas (velocidade realtime)

### v2.0

- Streaming Pipeline (25-35% mais rápido)
- Suporte a Cookies
- Auto-detecção yt-dlp

---

## Licença

MIT
