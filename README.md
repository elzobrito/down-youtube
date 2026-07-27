# YouTube Transcriber

Desktop application for downloading, transcribing, organizing, and exporting
**YouTube** videos (first-class), other sites **best-effort via yt-dlp** (e.g. Vimeo),
and local media files. It combines `yt-dlp`, FFmpeg, `whisper.cpp`, SQLite, and an
optional Ollama-powered chat workflow in a cross-platform Tkinter interface.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey.svg)

In one line:

```text
URL (video or playlist) or media file
  -> Expand playlist if needed
  -> Download/convert
  -> Transcribe (chunk long audio)
  -> Review / export / chat / long-term memory
```

### Playlists vs single videos (YouTube)

| URL shape | Behavior |
| --- | --- |
| `youtube.com/watch?v=ID` | One job for that video |
| `youtube.com/playlist?list=PL…` | Expanded with yt-dlp flat playlist → **N** watch URLs, processed one by one |
| `youtube.com/watch?v=ID&list=PL…` | **Default:** only that video (`list=` is context). UI can offer expanding the full playlist |
| Per-item download | Still uses yt-dlp `noplaylist` so each job is a single video |

Implementation: `core/url_resolver.py` (classify + expand); worker / Download / Queue / CLI all use the same expansion.

### Multi-site support (best-effort via yt-dlp)

YouTube remains the **primary, fully tested** path. Other HTTP(S) URLs are accepted
and handed to **yt-dlp** without YouTube-only extractor options
(`player_client`, etc.). Support quality depends on the yt-dlp extractor for that site.

| Input | Support level |
| --- | --- |
| **YouTube** (watch, Shorts, Music, playlists) | Full — expand, download, transcribe, library, LTM, quality presets |
| **Local files** (audio/video on disk) | Full — no URL required |
| **Other sites** (e.g. **Vimeo**, SoundCloud, and many yt-dlp extractors) | **Best-effort** — single URL and multi-entry sets/playlists when yt-dlp returns `entries` |
| **DRM / subscription video apps** (Netflix, Disney+, etc.) | **Not supported** — not a general “any video on the internet” downloader |

Notes:

- Non-YouTube downloads use generic yt-dlp format strings (and optional best-quality
  settings) **without** `extractor_args.youtube`.
- Multi-entry non-YouTube URLs are expanded via flat extract; UI confirms when N>1.
- Cookies still help on sites that require login; configure a cookies file in Settings.
- `source_site` in the library comes from yt-dlp `extractor_key` (or host fallback).
- Keep yt-dlp updated: extractors break when sites change.

## At A Glance

- Runs on Windows and Linux with the same Python entry point.
- Downloads YouTube audio or video through `yt-dlp` (full support), plus other
  sites **best-effort** via the same engine (not DRM); cookies for restricted sessions;
  single videos and playlists/sets.
- Processes local audio/video files without requiring a URL.
- Transcribes locally through `whisper.cpp`, using CPU or GPU builds depending
  on the installed backend.
- **Long audio (>60 minutes)** is automatically split into **30-minute chunks**,
  transcribed per piece, then merged with corrected SRT/TXT timestamps (reduces
  end-of-file Whisper hallucination loops on long interviews).
- Stores history, queues, settings, transcriptions, translations, and chat
  sessions in SQLite.
- Builds an optional **long-term memory** projection via
  [rag-sqlite](https://github.com/elzobrito/rag-sqlite) (`youtube_rag.sqlite` +
  `rag_corpus/`) for retrieval-augmented chat across the library.
- Exports transcripts as TXT, SRT, VTT, DOCX, and PDF.
- Provides an optional Ollama chat window for asking questions about completed
  transcriptions (with LTM `remember` scope: current video or full library).
- Includes a streaming pipeline that overlaps download and conversion work,
  plus traditional and keep-video modes.
- SQLite backup/restore uses the Online Backup API + integrity check + SHA-256.

## Feature Inventory

Implemented user-facing capabilities:

| Area | Available functions |
| --- | --- |
| Input | YouTube URL processing (single video **or playlist**), multi-site HTTP URLs best-effort via yt-dlp, local audio/video files, clipboard http(s) detection, CLI URL arguments, URL list files |
| Download | `yt-dlp` audio/video download (YouTube-aware opts only on YouTube hosts), cookies, progress hooks, streaming→traditional fallback, optional best video/audio quality settings |
| Conversion | FFmpeg audio extraction, normalization, WAV conversion, media duration detection |
| Transcription | `whisper.cpp` execution, language selection, thread/beam/best-of settings, optional GPU flag, duplicate detection by audio hash; **long audio (>60 min) → 30 min chunks**, merge with timestamp offsets, cancel/progress across chunks |
| Queue | Add URLs, import `.txt` lists, process pending/failed items, retry count tracking, remove selected items, clear queue |
| Library | Full-text search, language filter, preview pane, open full transcript, copy text, delete transcript, mark/unmark as used |
| Media access | Open saved audio or video files through the operating system |
| Export | TXT, SRT, VTT, DOCX, and PDF export for selected transcriptions |
| Chat | Ollama connection check, model configuration, streamed chat responses, persistent chat sessions per transcription; LTM retrieval (`remember`) with video vs full-library scope |
| History | Processing records, status tracking, failed-item reprocessing |
| Settings | FFmpeg path, whisper CLI path, model path, output directory, cookies path, language, performance, theme, notifications, streaming pipeline, Ollama URL/model, LTM health/backfill; long-audio defaults `whisper_long_audio_threshold_seconds=3600`, `whisper_chunk_seconds=1800`; **video_download_best_quality** (max yt-dlp video when keeping original) |
| Long-term memory | `core/rag_bridge.py` projects transcriptions to `rag_corpus/`, indexes via rag-sqlite CLI, manifest lookup for citations, durable index queue |
| Diagnostics | FFmpeg test button, stage progress panels, system stats, enhanced log with save/clear, NERD metrics panel |
| Notifications | Windows toast notifications through `winotify`; Linux desktop notifications through `notify-send` |
| Data safety | SQLite backup/restore via Online Backup API + `quick_check` + SHA-256 (Settings tab) |
| Portability | Portable-mode helpers through `portable.flag`; `.gitignore` excludes `data/`, sqlite, corpus |

Present in the codebase but not fully wired into the current UI:

| Area | Current state |
| --- | --- |
| Google Drive upload | Backend integration exists, but the Library button currently shows a placeholder message |
| Translation | Translator helper exists, but the Library button currently shows a placeholder message |
| Export all ZIP | Menu item exists, but the handler currently shows a placeholder message |
| `yt-dlp` updater | Update helper exists, but there is no visible UI flow in the current app |

## Quickstart

```bash
git clone https://github.com/elzobrito/down-youtube.git
cd down-youtube
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
| `yt-dlp` | Download and metadata extraction (YouTube + multi-site extractors) |
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
| Download | Process YouTube / multi-site URLs or local files, monitor progress, cancel work, inspect logs, and view NERD metrics |
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

## Long audio (chunked transcription)

Whisper models often **hallucinate repetitive text** near the end of very long
files (for example multi-hour interviews). To reduce that failure mode:

| Setting | Default | Meaning |
| --- | --- | --- |
| `whisper_long_audio_threshold_seconds` | `3600` | Only audios **longer than 60 minutes** are split |
| `whisper_chunk_seconds` | `1800` | Each piece is at most **30 minutes** |

Pipeline:

```text
duration > 60 min
  -> split WAV into N chunks of ≤30 min (pure wave I/O)
  -> whisper-cli once per chunk
  -> merge TXT + SRT with time offsets (chunk_i * 30 min)
  -> delete temporary chunk files
```

Audios **≤ 60 minutes** keep a single Whisper pass (no split).

Progress shows `Pedaço i/N`. Cancel stops the current chunk and cleans temps.
Chunked mode is wired from `core/worker.py` via `core/transcriber.py` and
`core/audio.py`.

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
| Long-audio threshold | `3600` seconds | Split only when longer than 60 min |
| Chunk length | `1800` seconds | 30-minute Whisper pieces |
| Best video quality | Off by default | Settings → “Melhor qualidade de video possivel”; with **Manter video**, uses `bv*+ba/b`, richer YouTube clients, merge **MKV** if needed. Off = legacy `bestvideo+bestaudio` → MP4. |
| Best audio quality | Off by default | Settings → “Melhor qualidade de audio possivel”: `ba/b` + better clients + sort by bitrate. Always builds **WAV 16 kHz mono** for Whisper; with **Manter audio**, also keeps HQ m4a/opus archive. Off = `bestaudio/best` → WAV. |
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
| Transcript ends with endless repeated phrases | Enable chunking (defaults on for >60 min) and reprocess; use a better Whisper model if ASR quality is still poor |
| `maximum recursion depth exceeded` on long audio | Fixed in current tree: chunk progress must not re-enter the progress callback; pull latest `core/transcriber.py` |
| Playlist only processes one video | Use a pure `playlist?list=` URL, or enable expand for `watch?v=&list=`; each item still downloads with `noplaylist` |

## Long-term memory (optional)

After transcriptions are saved, the app can project text into a local RAG index
for library-wide questions:

```bash
# smoke against the user RAG DB (default path under ~/.youtube_transcriber)
./scripts/memory_smoke.sh "your question"
```

See `docs/guides/youtube-long-term-memory.md` and
`docs/plans/PLAN-youtube-ltm-rag.md` for architecture, env vars
(`RAG_SQLITE_DB`), and acceptance notes. Requires the `rag-sqlite` CLI on
`PATH` (or configured under Settings).

## Project Layout

```text
down-youtube/
  main.py                         application entry point and CLI URL handling
  config.py                       settings and defaults (incl. long-audio / RAG)
  database.py                     SQLite storage for videos, transcripts, queue, history, and chat
  requirements.txt                Python runtime dependencies
  AGENTS.md                       ESAA agent contract (optional local governance)

  gui/
    app.py                        main window and tab orchestration
    tabs/
      download_tab.py             download and transcription workflow
      queue_tab.py                URL queue management
      library_tab.py              completed transcription library
      chat_tab.py                 Ollama chat + LTM remember
      history_tab.py              processing history
      settings_tab.py             app configuration + memory ops
    widgets/                      reusable Tkinter widgets
    themes/                       custom themes

  core/
    worker.py                     workflow orchestration and threading
    url_resolver.py               YouTube + multi-site classify/expand (playlists/sets)
    downloader.py                 yt-dlp integration (site-aware extractor_args)
    streaming_downloader.py       parallel download/conversion pipeline
    audio.py                      audio extract/normalize + long-audio split
    transcriber.py                whisper.cpp integration + chunked merge
    rag_bridge.py                 project/index transcriptions for rag-sqlite
    exporter.py                   TXT, SRT, VTT, DOCX, and PDF export
    ollama_client.py              Ollama REST client
    translator.py                 translation helpers
    updater.py                    update helpers

  integrations/
    notifications.py              platform notification integration

  utils/
    backup.py                     SQLite Online Backup API + hash
    portable.py                   portable-mode helpers

  docs/
    guides/                       operator guides (LTM, …)
    plans/                        design/plan docs

  scripts/
    memory_smoke.sh               health/stats/query smoke for YouTube RAG

  tests/
    test_multisite_download.py    site-aware yt-dlp opts (YouTube vs generic)
    test_multisite_playlist.py    multi-site playlist/set expansion
    test_transcriber_chunk.py     long-audio split/merge/cancel
    test_playlist_url.py          playlist expansion
    test_rag_bridge.py            LTM bridge
    …
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
