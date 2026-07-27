# Web API & Application Layer

Shared architecture:

```text
GUI (Tk) ─┐  (Download / Fila → create_batch_job / create_job)
CLI      ─┼→ app/ (jobs, library) → core/ + SQLite
API HTTP ─┘
```

The desktop GUI no longer instantiates `TranscriberWorker` directly; it enqueues
jobs and polls status/progress/log like CLI/API clients.

## Install API deps

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## CLI

```bash
# Enqueue a URL (returns job_id)
python -m cli jobs create --url 'https://x.com/user/status/ID'

# Wait for completion
python -m cli jobs create --url 'https://www.youtube.com/watch?v=...' --wait

# Status / list / cancel
python -m cli jobs status <job_id>
python -m cli jobs list
python -m cli jobs list --status failed
python -m cli jobs cancel <job_id>

# Library
python -m cli library list
python -m cli library list -q keyword

# HTTP server (default: 127.0.0.1:8765)
python -m cli serve
python -m cli serve --host 127.0.0.1 --port 8765
```

Legacy entry still works:

```bash
python main.py 'https://www.youtube.com/watch?v=...'
# (creates job + waits via app layer)
```

## HTTP API

Base URL: `http://127.0.0.1:8765`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/health` | Liveness (always open) |
| POST | `/v1/jobs` | Create job `{ "url": "..." }` or `{ "path": "..." }` → **202** `{ "job_id" }` |
| GET | `/v1/jobs` | List jobs (`?status=queued`) |
| GET | `/v1/jobs/{id}` | Job status / progress / log_tail |
| POST | `/v1/jobs/{id}/cancel` | Cancel queued or running |
| GET | `/v1/jobs/{id}/transcript` | Transcript when `done` (if linked) |
| GET | `/v1/library` | List transcriptions (`?q=`) |
| GET | `/v1/library/{id}` | Transcription detail |

### Examples

```bash
# Create job
curl -s -X POST http://127.0.0.1:8765/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://x.com/0C0RV0/status/2081873148215971856"}'

# Poll status
curl -s http://127.0.0.1:8765/v1/jobs/<job_id>
```

**Do not** pass media URLs as GET query parameters to trigger downloads.

## Optional API token

If `DOWN_YOUTUBE_API_TOKEN` is set, all routes except `/v1/health` require:

- Header `X-API-Key: <token>`, or
- Header `Authorization: Bearer <token>`

```bash
export DOWN_YOUTUBE_API_TOKEN='your-secret'
python -m cli serve

curl -X POST http://127.0.0.1:8765/v1/jobs \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-secret' \
  -d '{"url":"https://..."}'
```

## Security

- Default bind is **127.0.0.1** (local only).
- Do **not** expose the API on the public internet without auth, TLS, and rate limits.
- Headless jobs skip interactive “reprocess?” dialogs (`confirm_callback=False`).

## Job statuses

`queued` → `running` → `done` | `failed` | `cancelled`

One job runs at a time (v1).
