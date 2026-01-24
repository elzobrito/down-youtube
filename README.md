# 🎬 YouTube Transcriber

Ferramenta automatizada para download e transcrição de vídeos do YouTube usando **yt-dlp** e **Whisper.cpp**.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

## ✨ Funcionalidades

- **Download otimizado**: Baixa apenas o áudio (não o vídeo completo), economizando tempo e banda
- **Transcrição automática**: Integração com Whisper.cpp para transcrição em português
- **Processamento em lote**: Processa múltiplos vídeos a partir de uma lista
- **Limpeza automática**: Remove arquivos de áudio após transcrição para economizar espaço
- **Interface amigável**: Menu interativo ou uso via linha de comando

## 📋 Pré-requisitos

Antes de começar, você precisa ter instalado:

### 1. Python 3.8+

Baixe em [python.org](https://www.python.org/downloads/)

### 2. FFmpeg

**Windows:**
1. Baixe em [ffmpeg.org](https://ffmpeg.org/download.html) ou via [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
2. Extraia para `C:\FFMPEG`
3. Adicione `C:\FFMPEG\bin` ao PATH do sistema

**Linux:**
```bash
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 3. Whisper.cpp

Clone e compile o [whisper.cpp](https://github.com/ggerganov/whisper.cpp):

```bash
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
make

# Baixe o modelo (small recomendado para português)
./models/download-ggml-model.sh small
```

Adicione o executável (`main` ou `whisper-cli`) ao PATH ou especifique o caminho no script.

## 🚀 Instalação

1. Clone este repositório:
```bash
git clone https://github.com/seu-usuario/youtube-transcriber.git
cd youtube-transcriber
```

2. Instale as dependências:
```bash
pip install yt-dlp
```

3. Configure o script editando as variáveis no início do arquivo:
```python
FFMPEG_PATH = r'C:\FFMPEG\bin\ffmpeg.exe'  # Caminho do FFmpeg
WHISPER_CLI = 'whisper-cli'                 # ou 'main' dependendo da versão
WHISPER_MODEL = 'ggml-small.bin'            # Modelo do Whisper
WHISPER_LANGUAGE = 'portuguese'             # Idioma da transcrição
```

## 📖 Como Usar

### Modo Interativo

Execute sem argumentos para abrir o menu:

```bash
python youtube_transcriber.py
```

```
============================================================
🎬 YOUTUBE DOWNLOADER + WHISPER TRANSCRIBER
============================================================

Opções:
  1. Processar URL única
  2. Processar lista de URLs (arquivo .txt)
  3. Sair

Escolha uma opção (1/2/3):
```

### Modo Linha de Comando

Processe uma lista de vídeos diretamente:

```bash
# Básico
python youtube_transcriber.py lista.txt

# Com diretório de saída
python youtube_transcriber.py lista.txt ./transcricoes

# Mantendo os arquivos de áudio
python youtube_transcriber.py lista.txt ./transcricoes --manter
```

### Formato do Arquivo de Lista

Crie um arquivo `.txt` com uma URL por linha:

```text
# Minha playlist de transcrições
# Linhas com # são ignoradas

https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/watch?v=VIDEO_ID_2
https://youtu.be/VIDEO_ID_3
```

## 📁 Estrutura de Saída

Após o processamento, você terá:

```
📂 diretorio_saida/
├── 📄 Título do Vídeo 1.wav.txt
├── 📄 Título do Vídeo 2.wav.txt
└── 📄 Título do Vídeo 3.wav.txt
```

Os arquivos `.wav` são automaticamente removidos após a transcrição (a menos que use `--manter`).

## ⚙️ Modelos do Whisper

| Modelo | Tamanho | RAM Necessária | Qualidade |
|--------|---------|----------------|-----------|
| tiny | 75 MB | ~1 GB | Básica |
| base | 142 MB | ~1 GB | Boa |
| small | 466 MB | ~2 GB | **Recomendado** |
| medium | 1.5 GB | ~5 GB | Muito boa |
| large | 2.9 GB | ~10 GB | Excelente |

Para português, o modelo `small` oferece o melhor equilíbrio entre velocidade e qualidade.

## 🔧 Solução de Problemas

### "whisper-cli não encontrado"

Verifique se o Whisper.cpp está no PATH ou ajuste a variável `WHISPER_CLI`:

```python
WHISPER_CLI = r'C:\whisper.cpp\main.exe'  # Windows
WHISPER_CLI = '/home/user/whisper.cpp/main'  # Linux
```

### "ffmpeg não encontrado"

Certifique-se de que o FFmpeg está instalado e o caminho está correto:

```python
FFMPEG_PATH = r'C:\FFMPEG\bin\ffmpeg.exe'  # Windows
FFMPEG_PATH = '/usr/bin/ffmpeg'  # Linux
```

### Erro de codificação no título

Se houver problemas com caracteres especiais, o script sanitiza automaticamente os nomes dos arquivos.

### Vídeo privado ou indisponível

O script mostrará um erro e continuará para o próximo vídeo da lista.

## 📝 Exemplos de Uso

**Transcrever uma palestra:**
```bash
python youtube_transcriber.py
# Opção 1 → Cole a URL → Enter para pasta atual → N para não manter áudio
```

**Transcrever playlist de um curso:**
```bash
# Crie curso.txt com todas as URLs
python youtube_transcriber.py curso.txt ./curso_transcricoes
```

**Transcrever e manter áudios para revisão:**
```bash
python youtube_transcriber.py videos.txt ./saida --manter
```

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para:

1. Fazer um fork do projeto
2. Criar uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/nova-funcionalidade`)
5. Abrir um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 🙏 Agradecimentos

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - Download de vídeos
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) - Transcrição de áudio
- [FFmpeg](https://ffmpeg.org/) - Processamento de mídia

---

Feito com ❤️ para a comunidade brasileira
