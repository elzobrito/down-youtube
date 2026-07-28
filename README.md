# YouTube Transcriber (down-youtube)

Local-first tool for downloading, transcribing, organizing, and exporting media.
**YouTube** is first-class; other sites (e.g. Vimeo, X/Twitter) work **best-effort**
via `yt-dlp`. Local files are supported. Stack: `yt-dlp`, FFmpeg, `whisper.cpp`,
SQLite, optional Ollama + [rag-sqlite](https://github.com/elzobrito/rag-sqlite).

<p align="center">
  <img src="assets/icon.svg" alt="YouTube Transcriber icon" width="128" height="128"/>
</p>

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

## Architecture (GUI + CLI + API)

All three interfaces share one application layer and one SQLite database:

```text
┌─────────────┐  ┌─────────────┐  ┌──────────────────┐
│  GUI (Tk)   │  │  CLI        │  │  API HTTP        │
│  desktop    │  │  scripts    │  │  FastAPI         │
└──────┬──────┘  └──────┬──────┘  └────────┬─────────┘
       │                │                   │
       └────────────────┼───────────────────┘
                        ▼
              ┌─────────────────────┐
              │  app/               │  jobs queue, library facade
              │  (application layer)│
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │  core/ + database   │  worker, yt-dlp, whisper, SQLite
              └─────────────────────┘
```

| Interface | Entry | Notes |
| --- | --- | --- |
| **Desktop GUI** | `python main.py` | Tkinter; Download/Fila enqueue via `app.jobs` (same queue as CLI/API) |
| **CLI jobs** | `python -m cli jobs …` | Create / status / list / cancel |
| **HTTP API** | `python -m cli serve` | FastAPI default `http://127.0.0.1:8765` |
| **Sync CLI** | `python main.py URL…` | Creates a job and waits for completion |

### Job lifecycle

```text
queued → running → done | failed | cancelled
```

- One job runs at a time (v1).
- Mutations use **POST**; status uses **GET** (never trigger downloads via GET).
- Optional API auth: set `DOWN_YOUTUBE_API_TOKEN` and send `X-API-Key` or `Authorization: Bearer …`.
- Full HTTP/CLI reference: **[docs/guides/web-api.md](docs/guides/web-api.md)**.

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
| **Other sites** (e.g. **Vimeo**, **X/Twitter** status URLs, SoundCloud) | **Best-effort** via yt-dlp — single URL and multi-entry sets when `entries` exist |
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
- Exports transcripts as TXT, SRT, VTT, DOCX, PDF, and Markdown.
- Can create a local, reviewable **Phi-4 Mini** post-ASR draft while keeping
  the original transcription immutable.
- Provides an optional Ollama chat window for asking questions about completed
  transcriptions (with LTM `remember` scope: current video or full library).
- Includes a streaming pipeline that overlaps download and conversion work,
  plus traditional and keep-video modes.
- **Shared job queue** across GUI, CLI, and HTTP API (`app.jobs` + `jobs` table).
- **Polished Light/Dark (Custom)** ttk themes on the desktop UI.
- SQLite backup/restore uses the Online Backup API + integrity check + SHA-256.

## Feature Inventory

Implemented user-facing capabilities:

| Area | Available functions |
| --- | --- |
| Input | YouTube URL processing (single video **or playlist**), multi-site HTTP URLs best-effort via yt-dlp (incl. X/Twitter status URLs), local audio/video files, clipboard http(s) detection, CLI/API job create |
| Jobs / API | Async job queue (`app.jobs`); CLI `python -m cli`; FastAPI `POST/GET /v1/jobs`, `GET /v1/library`, `GET /v1/health` |
| Download | `yt-dlp` audio/video download (YouTube-aware opts only on YouTube hosts), cookies, progress hooks, streaming→traditional fallback, optional best video/audio quality settings |
| Conversion | FFmpeg audio extraction, normalization, WAV conversion, media duration detection |
| Transcription | `whisper.cpp` execution, language selection, thread/beam/best-of settings, optional GPU flag, duplicate detection by audio hash; **long audio (>60 min) → 30 min chunks**, merge with timestamp offsets, cancel/progress across chunks |
| Queue | Add URLs, import `.txt` lists, process pending/failed items, retry count tracking, remove selected items, clear queue |
| Library | Full-text search, language filter, Original/Aprimorada/Estudo preview, local IA draft/review history, open/copy/delete, mark/unmark as used |
| Media access | Open saved audio or video files through the operating system |
| Export | TXT, SRT, VTT, DOCX, PDF, and Markdown export for the version displayed |
| Chat | Ollama connection check, model configuration, streamed chat responses, persistent chat sessions per transcription; LTM retrieval (`remember`) with video vs full-library scope |
| History | Processing records, status tracking, failed-item reprocessing |
| Settings | FFmpeg path, whisper CLI path, model path, output directory, cookies path, language, performance, **Light/Dark (Custom)** themes, notifications, streaming pipeline, independent Ollama chat/improvement models, LTM health/backfill; long-audio defaults `whisper_long_audio_threshold_seconds=3600`, `whisper_chunk_seconds=1800`; **video_download_best_quality** (max yt-dlp video when keeping original) |
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

Install dependencies and start the **desktop** app:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

### CLI (jobs)

```bash
# Enqueue (prints job_id)
python -m cli jobs create --url "https://www.youtube.com/watch?v=..."
python -m cli jobs create --url "https://x.com/user/status/1234567890"
python -m cli jobs create --path "/path/to/audio.mp3"

# Wait until finished (exit code 1 on failure)
python -m cli jobs create --url "https://..." --wait

python -m cli jobs status <job_id>
python -m cli jobs list
python -m cli jobs list --status failed
python -m cli jobs cancel <job_id>
python -m cli library list
python -m cli library list -q keyword
```

### HTTP API

```bash
# Default: 127.0.0.1:8765 (local only)
python -m cli serve

curl -s -X POST http://127.0.0.1:8765/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=..."}'

curl -s http://127.0.0.1:8765/v1/jobs/<job_id>
curl -s http://127.0.0.1:8765/v1/health
```

Optional token:

```bash
export DOWN_YOUTUBE_API_TOKEN='your-secret'
python -m cli serve
# then: -H 'X-API-Key: your-secret'
```

### Sync URL mode (still supported)

```bash
python main.py "https://www.youtube.com/watch?v=..."
python main.py --url "https://www.youtube.com/watch?v=..."
python main.py --urls urls.txt
```

When no URL is passed, the desktop interface opens. See
[docs/guides/web-api.md](docs/guides/web-api.md) for the full API surface.

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

Ollama is optional and supports both Chat IA and the post-ASR improvement
workflow. The two features have independent model settings. For the default
improvement model:

```bash
ollama pull phi4-mini:latest
```

In Biblioteca, select a transcription and choose **Aprimorar IA**. Processing
runs sequentially in background chunks and creates a draft; it never replaces
the original. Review each proposed correction/outtake, then either approve the
selection or reject the draft. Only an approved revision becomes the effective
text used by search, Chat IA, and RAG. **Usar original** deactivates that
revision and schedules the original for RAG reindexing.

The study Markdown is derived deterministically from the faithful corrected
text. Commands found in speech are displayed as text only and are never
executed. Unknown lexical rewrites remain unselected until a person approves
them.

## Desktop Launcher

A Linux `.desktop` entry can point at a small wrapper on your `PATH`, for example:

```text
~/.local/bin/youtube-transcriber
```

Typical wrapper shape (machine-agnostic paths — adjust to your install):

```bash
#!/usr/bin/env bash
set -euo pipefail
# Prefer a dedicated venv, or fall back to the project checkout:
ROOT="${DOWN_YOUTUBE_ROOT:-$HOME/desenvolvimento/down-youtube}"
VENV="${DOWN_YOUTUBE_VENV:-$HOME/.local/opt/down-youtube-venv}"
if [[ -x "$VENV/bin/python" ]]; then
  exec "$VENV/bin/python" "$ROOT/main.py" "$@"
fi
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" "$ROOT/main.py" "$@"
fi
exec python3 "$ROOT/main.py" "$@"
```

Optional env vars:

| Variable | Purpose |
| --- | --- |
| `DOWN_YOUTUBE_ROOT` | Path to the repository checkout |
| `DOWN_YOUTUBE_VENV` | Path to the Python virtualenv used by the launcher |

Icon assets live under `assets/` (`icon.svg`, `icon.png`). A sample desktop file is
`assets/youtube-transcriber.desktop` — copy it to `~/.local/share/applications/`
and set `Exec=` / `Icon=` to paths that exist on **your** machine.

If the launcher does not open, check that `Exec` points to an existing script and
that the venv (or system) Python can import the project dependencies.

## Dependencies

| Package | Purpose |
| --- | --- |
| `yt-dlp` | Download and metadata extraction (YouTube + multi-site extractors) |
| `customtkinter` | Desktop UI components (optional/legacy widgets) |
| `Pillow` | Image handling |
| `python-docx` | DOCX export |
| `reportlab` | PDF export |
| `deep-translator` | Translation support |
| `google-auth-oauthlib` | Google OAuth support for Drive integration |
| `google-api-python-client` | Google Drive API support |
| `ttkthemes` | Tkinter themes |
| `fastapi` / `uvicorn` / `pydantic` | HTTP API (`python -m cli serve`) |
| `httpx` | API tests / HTTP client support |
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
| ASR audio preprocess | `off` by default | Settings → “Pre-processamento ASR”: **Desligado** / **Leve** / **Fala** (`off` / `light` / `speech`). Optional FFmpeg filters before Whisper (loudnorm, light denoise). Does **not** separate music beds or overlapping speakers. For difficult audio prefer a **medium** or **large** Whisper model (no automatic model switch). Snapshot is frozen per job/batch. |
| Output directory | A user-writable folder | For example `~/Downloads/Transcriptions` on Linux or a user folder on Windows |

### ASR audio preprocess (optional)

Whisper still struggles with loud music and mixed speech. The app can optionally run FFmpeg filters on the **work WAV** (16 kHz mono) before transcription:

| Preset | What it does |
| --- | --- |
| `off` | Legacy path — no extra filters (default) |
| `light` | High-pass / low-pass + loudness normalize |
| `speech` | Stronger speech band filters + denoise + dynamic norm (falls back to `light`/`off` if FFmpeg filters fail) |

Provenance (`source_audio_hash`, applied preset, filter graph) is stored with the transcription. Original local files, downloaded videos, and HQ audio archives are never modified — only the work WAV.

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
| Desktop launcher does not open | Check `Exec=` in the `.desktop` file, `~/.local/bin/youtube-transcriber` (or your wrapper), and `DOWN_YOUTUBE_ROOT` / `DOWN_YOUTUBE_VENV` |
| `customtkinter` not found | Reinstall dependencies in the launcher virtual environment (`pip install -r requirements.txt`) |
| YouTube asks for sign-in or bot confirmation | Export fresh cookies and configure them in Settings |
| HTTP 403 | Try fresh cookies, a different network, or a VPN |
| FFmpeg not found | Install FFmpeg or configure the exact binary path |
| GPU does not work | Rebuild `whisper.cpp` with the desired GPU backend, or disable GPU mode |
| Ollama does not connect | Confirm that `ollama serve` is running and the configured model exists |
| Chat returns no response | Check the Ollama URL, model name, and server logs |
| Transcript ends with endless repeated phrases | Enable chunking (defaults on for >60 min) and reprocess; use a better Whisper model if ASR quality is still poor |
| Poor ASR with background music/noise | Try Settings → Pre-processamento ASR → Leve or Fala; use medium/large model. Filters do not separate music or overlapping voices |
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
  main.py                         GUI entry + sync URL mode (app.jobs create+wait)
  config.py                       settings and defaults (incl. long-audio / RAG)
  database.py                     SQLite: videos, transcripts, queue, history, chat, jobs
  requirements.txt                Python runtime dependencies
  AGENTS.md                       ESAA agent contract (optional local governance)

  assets/
    icon.svg                      app icon (vector source)
    icon-mono.svg                 monochrome variant (currentColor)
    icon.png / icon-*.png         raster exports for window / desktop launchers

  app/                            application layer (shared by GUI, CLI, API)
    jobs.py                       job queue, worker bridge, batch jobs, hooks
    library.py                    library read facade
    models.py                     Job dataclass

  cli/                            python -m cli (jobs / library / serve)
  api/                            FastAPI app (POST/GET /v1/jobs, library, health)

  gui/
    app.py                        main window; enqueues work via app.jobs
    tabs/
      download_tab.py             URL hero + progress cards
      queue_tab.py                desktop URL queue (UI)
      library_tab.py              completed transcription library
      chat_tab.py                 Ollama chat + LTM remember
      history_tab.py              processing history
      settings_tab.py             paths, quality, theme Light/Dark (Custom)
    widgets/                      reusable Tkinter widgets
    themes/                       polished ttk Light/Dark manager

  core/
    worker.py                     pipeline orchestration (used by app.jobs)
    url_resolver.py               YouTube + multi-site classify/expand
    downloader.py                 yt-dlp (site-aware extractor_args)
    streaming_downloader.py       parallel download/conversion
    audio.py                      extract/normalize + long-audio split
    transcriber.py                whisper.cpp + chunked merge
    rag_bridge.py                 LTM projection for rag-sqlite
    exporter.py                   TXT, SRT, VTT, DOCX, PDF
    ollama_client.py              Ollama REST client

  integrations/
    notifications.py

  utils/
    backup.py                     SQLite Online Backup API + hash
    portable.py

  docs/
    guides/
      web-api.md                  CLI + HTTP API guide
      youtube-long-term-memory.md
    plans/

  scripts/
    memory_smoke.sh

  tests/
    test_app_jobs.py              job store / queue
    test_app_worker_bridge.py
    test_gui_app_jobs.py          GUI batch enqueue
    test_api_jobs.py / test_api_auth.py
    test_cli_jobs.py
    test_multisite_*.py
    test_theme.py
    …
```

## Database

Default path: `~/.youtube_transcriber/youtube_transcriber.db` (or portable `data/`).

| Table | Purpose |
| --- | --- |
| `settings` | Key-value app configuration |
| `videos` | Video metadata, source URLs, channels, duration, and file paths |
| `transcriptions` | Transcript text, segment JSON, audio hash, and usage flag |
| `transcription_revisions` | Immutable-origin improvement drafts, approvals, selected proposals, faithful segments, and study Markdown |
| `translations` | Translated transcript text |
| `history` | Processing attempts, status, and timing |
| `queue` | Desktop “Fila” tab pending/failed URLs |
| `jobs` | **Shared** async job queue for GUI, CLI, and API |
| `chat_sessions` | Ollama chat sessions per transcription |
| `chat_messages` | Individual chat messages |

## Changelog

### v3.2 — Application layer (GUI + CLI + API)

- Shared `app/` layer: job queue, library facade, single worker bridge to `core.worker`.
- CLI: `python -m cli jobs|library|serve`.
- HTTP API: FastAPI on `127.0.0.1:8765` by default; optional `DOWN_YOUTUBE_API_TOKEN`.
- Desktop GUI migrates Download/Fila to `app.jobs` (same queue as CLI/API).
- Multi-site best-effort via yt-dlp (Vimeo, X/Twitter status URLs, etc.).
- Polished Light/Dark (Custom) ttk themes; Download/Biblioteca layout polish.
- Best video/audio quality options in Settings.
- App icon: `assets/icon.svg` (+ PNG exports); window icon on GUI start.
- Docs: [docs/guides/web-api.md](docs/guides/web-api.md).

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
