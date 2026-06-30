# YouTube Transcriber

Desktop application for downloading, transcribing, organizing, and exporting
YouTube videos and local media files. It combines `yt-dlp`, FFmpeg,
`whisper.cpp`, SQLite, and an optional Ollama-powered chat workflow in a
cross-platform Tkinter interface.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey.svg)

In one line:

```text
URL or media file -> Download/convert -> Transcribe -> Review/export/chat
```

## At A Glance

- Runs on Windows and Linux with the same Python entry point.
- Downloads YouTube audio or video through `yt-dlp`, with cookies support for
  restricted sessions.
- Processes local audio/video files without requiring a YouTube URL.
- Transcribes locally through `whisper.cpp`, using CPU or GPU builds depending
  on the installed backend.
- Stores history, queues, settings, transcriptions, translations, and chat
  sessions in SQLite.
- Exports transcripts as TXT, SRT, VTT, DOCX, and PDF.
- Provides an optional Ollama chat window for asking questions about completed
  transcriptions.
- Includes a streaming pipeline that overlaps download and conversion work,
  plus traditional and keep-video modes.

## Feature Inventory

Implemented user-facing capabilities:

| Area | Available functions |
| --- | --- |
| Input | YouTube URL processing, local audio/video file processing, clipboard URL detection, CLI URL arguments, URL list files |
| Download | `yt-dlp` audio download, video download when keeping MP4, cookies file support, progress hooks, automatic fallback from streaming to traditional mode |
| Conversion | FFmpeg audio extraction, normalization, WAV conversion, media duration detection |
| Transcription | `whisper.cpp` execution, language selection, thread/beam/best-of settings, optional GPU flag, duplicate detection by audio hash |
| Queue | Add URLs, import `.txt` lists, process pending/failed items, retry count tracking, remove selected items, clear queue |
| Library | Full-text search, language filter, preview pane, open full transcript, copy text, delete transcript, mark/unmark as used |
| Media access | Open saved audio or video files through the operating system |
| Export | TXT, SRT, VTT, DOCX, and PDF export for selected transcriptions |
| Chat | Ollama connection check, model configuration, streamed chat responses, persistent chat sessions per transcription |
| History | Processing records, status tracking, failed-item reprocessing |
| Settings | FFmpeg path, whisper CLI path, model path, output directory, cookies path, language, performance, theme, notifications, streaming pipeline, Ollama URL/model |
| Diagnostics | FFmpeg test button, stage progress panels, system stats, enhanced log with save/clear, NERD metrics panel |
| Notifications | Windows toast notifications through `winotify`; Linux desktop notifications through `notify-send` |
| Data safety | SQLite backup and restore from the Settings tab |
| Portability | Portable-mode helpers through `portable.flag` |

Present in the codebase but not fully wired into the current UI:

| Area | Current state |
| --- | --- |
| Google Drive upload | Backend integration exists, but the Library button currently shows a placeholder message |
| Translation | Translator helper exists, but the Library button currently shows a placeholder message |
| Export all ZIP | Menu item exists, but the handler currently shows a placeholder message |
| `yt-dlp` updater | Update helper exists, but there is no visible UI flow in the current app |

## Quickstart

```bash
git clone https://github.com/seu-usuario/youtube-transcriber.git
cd youtube-transcriber
python -m venv .venv
```

Activate the environment:

```bash
# Linux
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install dependencies and start the app:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

The same entry point also accepts CLI URLs:

```bash
python main.py "https://www.youtube.com/watch?v=..."
python main.py --url "https://www.youtube.com/watch?v=..."
python main.py --urls urls.txt
```

When no URL is passed, the desktop interface opens.

## Requirements

### Python

Python 3.8 or newer is required.

```bash
python --version
```

### FFmpeg

FFmpeg must be installed and available on `PATH`, or configured in the app
settings.

```bash
ffmpeg -version
```

Common install paths:

| Platform | Typical setup |
| --- | --- |
| Linux | Install with the system package manager, for example `sudo apt install ffmpeg` |
| Windows | Install a Windows build and add its `bin` directory to `PATH` |

### whisper.cpp

Build or install `whisper.cpp`, then download a model:

```bash
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build --config Release
./models/download-ggml-model.sh base
```

Configure the app with the path to the `whisper-cli` binary and the selected
model file.

### Ollama

Ollama is optional and only needed for the chat feature.

```bash
ollama pull llama3
```

## Desktop Launcher

The Linux desktop launcher `YouTube Transcriber` calls:

```text
/home/elzobrito/.local/bin/youtube-transcriber
```

On this workstation, that wrapper intentionally uses the local virtual
environment:

```text
/home/elzobrito/.local/opt/down-youtube-venv
```

This keeps the launcher independent from a project `.venv` stored inside a
Google Drive-synchronized folder. If the launcher stops opening, first verify
that the wrapper points to an existing Python executable.

## Dependencies

| Package | Purpose |
| --- | --- |
| `yt-dlp` | YouTube download and metadata extraction |
| `customtkinter` | Desktop UI components |
| `Pillow` | Image handling |
| `python-docx` | DOCX export |
| `reportlab` | PDF export |
| `deep-translator` | Translation support |
| `google-auth-oauthlib` | Google OAuth support for Drive integration |
| `google-api-python-client` | Google Drive API support |
| `ttkthemes` | Tkinter themes |
| `winotify` | Optional Windows toast notifications |

## Interface

The app is organized around the main transcription workflow.

| Area | Purpose |
| --- | --- |
| Download | Process YouTube URLs or local files, monitor progress, cancel work, inspect logs, and view NERD metrics |
| Queue | Add URLs, import `.txt` lists, process pending/failed items, remove items, and clear the queue |
| Library | Search, filter, preview, open, copy, delete, export, and mark completed transcriptions as used |
| Chat | Ask Ollama questions about a selected transcription and keep persistent sessions |
| History | Review previous processing attempts and rerun failed items |
| Settings | Configure paths, cookies, language, performance, media retention, notifications, streaming, themes, Ollama, and backups |

Useful shortcuts:

| Shortcut | Action |
| --- | --- |
| `Enter` | Process the current URL |
| `Escape` | Cancel or clear the current field |
| `Ctrl+L` | Focus the URL field |

## Streaming Pipeline

The streaming pipeline overlaps download and conversion work to reduce total
processing time.

```text
Traditional:  Download ----- 30s -> Convert -- 10s = 40s
Streaming:    Download ----- 30s
              Convert  ---- 10s                 = 30s
```

Enable it from:

```text
Settings -> Streaming Pipeline -> Save
```

## YouTube Cookies

Cookies may be required when YouTube returns:

```text
ERROR: Sign in to confirm you're not a bot
```

Export cookies from the browser session where YouTube is already logged in,
then configure the cookies file in the app settings.

Cookies expire periodically, so repeat the export when downloads start failing
with authentication or bot-check errors.

## Recommended Settings

| Setting | Typical value | Notes |
| --- | --- | --- |
| Threads | Number of physical CPU cores | Use `0` for automatic behavior when supported |
| Beam size | `5` | Balanced quality and speed |
| Best of | `1` | Default fast path |
| GPU CUDA | Enabled only with a CUDA-enabled `whisper.cpp` build | Leave disabled for CPU builds |
| Output directory | A user-writable folder | For example `~/Downloads/Transcriptions` on Linux or a user folder on Windows |

Configure these paths in the app instead of hard-coding platform-specific
defaults:

| Path | Example |
| --- | --- |
| FFmpeg | `ffmpeg` when available on `PATH`, otherwise the full binary path |
| Whisper CLI | Full path to `whisper-cli` or `whisper-cli.exe` |
| Model | Full path to a `ggml-*.bin` model file |
| Output | Any writable directory for generated audio, video, and transcript files |

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `yt-dlp` not found | Install dependencies with `python -m pip install -r requirements.txt` |
| Desktop launcher does not open | Check `/home/elzobrito/.local/bin/youtube-transcriber` and the configured virtual environment path |
| `customtkinter` not found | Reinstall dependencies in the launcher virtual environment |
| YouTube asks for sign-in or bot confirmation | Export fresh cookies and configure them in Settings |
| HTTP 403 | Try fresh cookies, a different network, or a VPN |
| FFmpeg not found | Install FFmpeg or configure the exact binary path |
| GPU does not work | Rebuild `whisper.cpp` with the desired GPU backend, or disable GPU mode |
| Ollama does not connect | Confirm that `ollama serve` is running and the configured model exists |
| Chat returns no response | Check the Ollama URL, model name, and server logs |

## Project Layout

```text
youtube-transcriber/
  main.py                         application entry point and CLI URL handling
  config.py                       settings and defaults
  database.py                     SQLite storage for videos, transcripts, queue, history, and chat
  requirements.txt                Python runtime dependencies

  gui/
    app.py                        main window and tab orchestration
    tabs/
      download_tab.py             download and transcription workflow
      queue_tab.py                URL queue management
      library_tab.py              completed transcription library
      chat_tab.py                 Ollama chat window
      history_tab.py              processing history
      settings_tab.py             app configuration
    widgets/                      reusable Tkinter widgets
    themes/                       custom themes

  core/
    worker.py                     workflow orchestration and threading
    downloader.py                 yt-dlp integration
    streaming_downloader.py       parallel download/conversion pipeline
    audio.py                      audio extraction and normalization
    transcriber.py                whisper.cpp integration
    exporter.py                   TXT, SRT, VTT, DOCX, and PDF export
    ollama_client.py              Ollama REST client
    translator.py                 translation helpers
    updater.py                    update helpers

  integrations/
    notifications.py              platform notification integration

  utils/
    backup.py                     database backup and restore
    portable.py                   portable-mode helpers
```

## Database

The app uses SQLite with tables for:

| Table | Purpose |
| --- | --- |
| `settings` | Key-value app configuration |
| `videos` | Video metadata, source URLs, channels, duration, and file paths |
| `transcriptions` | Transcript text, segment JSON, audio hash, and usage flag |
| `translations` | Translated transcript text |
| `history` | Processing attempts, status, and timing |
| `queue` | Pending and completed queued URLs |
| `chat_sessions` | Ollama chat sessions per transcription |
| `chat_messages` | Individual chat messages |

## Changelog

### v3.0

- Added Ollama chat sessions with streamed responses and transcript context.
- Added SRT and VTT export with timecodes.
- Added context menus, hover tooltips, temporary status flashes, and enhanced logs.
- Added library usage flags, language filters, and direct access to original
  audio/video files.
- Added duplicate detection by audio hash.
- Added database backup and restore.

### v2.1

- Added a custom dark theme.
- Added NERD mode with detailed processing metrics.
- Added notification hooks.
- Added a functional conversion progress bar.
- Added real-time performance statistics.

### v2.0

- Added the streaming pipeline.
- Added cookies support.
- Added automatic `yt-dlp` detection.

## License

MIT
