# YouTube Transcriber

Aplicativo com interface grafica para baixar audio, transcrever com whisper.cpp e armazenar tudo no SQLite. Fila persistente, biblioteca de transcricoes, historico com reprocessamento e suporte a arquivos locais.

## Recursos

- Download via yt-dlp (audio ou video + extracao de audio)
- Transcricao com whisper.cpp (modelo definido pelo usuario)
- Fila persistente no banco (status pending/processing/done/failed)
- Biblioteca com busca e exportacao (TXT, SRT, VTT, DOCX, PDF)
- Historico com reprocessamento e abertura de midia
- Suporte a arquivo local (video ou audio)
- Modo portatil com data/ local

## Requisitos

- Python 3.8+
- FFmpeg
- whisper.cpp v1.8.3 (whisper-cli)
- yt-dlp

## Instalacao

```bash
git clone https://github.com/seu-usuario/down-youtube.git
cd down-youtube
pip install -r requirements.txt
```

## Executar

```bash
python main.py
```

Ou:

```bash
python down_youtube.py
```

## Configuracao

Abra a aba Configuracoes e ajuste:

- FFmpeg: caminho do executavel
- Whisper CLI: caminho do whisper-cli
- Modelo Whisper: arquivo .bin do modelo
- Idioma: ex. portuguese
- Threads: 0 = auto
- Beam size / Best of
- Manter audio (opcional)
- Manter video (opcional, usa MP4)

Observacao: usar GPU requer whisper-cli compilado com CUDA. Caso contrario, o app usa CPU normalmente.

## Uso (URL)

1. Cole a URL na aba Download
2. Clique em Processar
3. A transcricao entra na Biblioteca e no Historico

## Uso (Arquivo local)

1. Clique em Arquivo local na aba Download
2. Selecione um video ou audio
3. O app converte para WAV 16k mono e transcreve

## Fila persistente

- A aba Fila salva os itens no SQLite
- Itens processados ficam como done/failed
- Processar Fila processa apenas pending/failed
- Use Limpar Fila para remover tudo

## Banco de dados

O SQLite fica em:

- Normal: %USERPROFILE%/.youtube_transcriber/youtube_transcriber.db
- Portatil: ./data/youtube_transcriber.db (crie um arquivo portable.flag na raiz)

## Saida

- Arquivos .txt sao criados no diretorio de saida
- Audio e video sao removidos por padrao, a menos que voce marque as opcoes de manter

## Solucao de problemas

### Erro: unknown argument

Sua versao do whisper-cli pode nao aceitar certas flags. Ajuste Beam size / Best of nas Configuracoes.

### Whisper-cli nao encontrado

Verifique o caminho em Configuracoes ou adicione ao PATH.

### FFmpeg nao encontrado

Instale o FFmpeg e configure o caminho no app.

### GPU nao funciona

O whisper.cpp precisa ser compilado com CUDA (GGML_CUDA=1). Se nao estiver, o app roda em CPU.

## Licenca

MIT

## Creditos

- yt-dlp
- whisper.cpp
- FFmpeg
