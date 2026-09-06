# Inscora — Chandra OCR Edition

AI exam correction pipeline for real classroom use: teachers photograph student
answer sheets with any phone, and this service runs **Chandra OCR (Datalab) →
local LLM grading** and returns structured marks, confidence and feedback.

Fully local, zero paid APIs (unless you opt into the Datalab hosted API), runs
on a consumer laptop and transfers unchanged to a college server.

## Pipeline

```
phone photo (JPEG/PNG/HEIC)
  → HEIC conversion (pillow-heif)
  → hard resize ≤ 2000px  [guards the >2300px silent-crash bug]
  → blur/quality check    [flags blurry scans for re-shoot]
  → Chandra OCR           [ollama (local) or Datalab API, keep_alive=0 → unloaded]
  → grading LLM           [llama3.2:3b via ollama, JSON-constrained, keep_alive=0]
  → results/{id}_grade.json + live UI table
```

**Golden rule enforced in code:** models load and unload sequentially
(`keep_alive: 0` on every Ollama call) so OCR and grading never share VRAM.

## Setup (Windows laptop)

```bat
cd chandra-version
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

1. Install [Ollama](https://ollama.com), then pull the models:

```bash
ollama pull llama3.2:3b        # grading
# Chandra OCR GGUF: import from HuggingFace into Ollama, e.g.
ollama pull hf.co/datalab-to/chandra-ocr-2-GGUF:Q4_K_M
# then set OCR_MODEL in .env to the exact tag shown by `ollama list`
```

2. Start the service:

```bat
run.bat            :: or: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

3. Open `http://localhost:8000` on the laptop, or from any phone on the same
   Wi-Fi use `http://<laptop-LAN-IP>:8000`. For remote/phone testing over the
   internet, tunnel it:

```bash
ssh -p 443 -R0:localhost:8000 free.pinggy.io
```

## Operating modes

| Mode | When | Config |
|---|---|---|
| `ollama` (default) | Laptop/server with (or without) GPU — everything local | `OCR_MODE=ollama`, `OCR_MODEL=<ollama tag>` |
| `api` | Machine with no GPU — OCR goes to Datalab's hosted API, grading stays local | `OCR_MODE=api`, `DATALAB_API_KEY=...` |

## API

- `GET  /api/health` — engine status + installed Ollama models
- `POST /api/grade` — multipart: `files[]` (1–20 images) + `rubric` text or
  `rubric_file` → full result JSON (also saved to `results/`)
- `GET  /api/results` / `GET /api/results/{name}` — list/fetch saved results
- `GET  /docs` — interactive Swagger UI (manual testing without Postman)

Every result carries **confidence + flags** (blurry scan, resized page, low OCR
confidence, low grading confidence). Anything amber or red is teacher-review
first — nothing auto-finalizes below the confidence thresholds.

## Safety / hardening

- Ollama host is SSRF-validated (http(s) + loopback/private IP only, no redirects)
- Upload size / page-count caps (20 MB, 20 pages)
- Result filenames sanitized against path traversal
- Optional Sentry (`SENTRY_DSN` in `.env`), sample-rate 0.1

## Tests

```bash
python -m pytest tests/ -v
```

All pipeline stages are tested with mocked model calls — no GPU or Ollama
needed to validate the service contract.

## Using your real test data

Point the phone/web UI at your 60+ HEIC answer sheets
(`Answer papers-...` folder). HEIC is converted automatically as long as
`pillow-heif` is installed (it's in requirements.txt). For batch offline runs:

```bash
python -m uvicorn app.main:app   # then POST via /docs or curl
```
