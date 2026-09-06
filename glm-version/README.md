# Inscora — GLM-OCR Edition

AI exam correction pipeline for real classroom use: teachers photograph student
answer sheets with any phone, and this service runs **GLM-OCR (0.9B, two-pass)
→ local LLM grading** and returns structured marks, confidence and feedback.

Fully local, zero paid APIs, runs on a consumer laptop and transfers unchanged
to a college server. GLM-OCR scores ~94.6 on OmniDocBench and reconstructs
tables and LaTeX math well — ideal for math/science papers.

## Pipeline

```
phone photo (JPEG/PNG/HEIC)
  → HEIC conversion (pillow-heif)
  → hard resize ≤ 2000px   [guards the >2300px silent-crash bug]
  → blur/quality check     [flags blurry scans for re-shoot]
  → GLM-OCR pass 1         [temperature 0, keep_alive=0 → unloaded]
  → pass 2 (weak pages)    [high-accuracy prompt; better reading kept]
  → grading LLM            [llama3.2:3b via ollama, JSON-constrained, keep_alive=0]
  → results/{id}_grade.json + live UI table
```

**Golden rule enforced in code:** models load and unload sequentially
(`keep_alive: 0` on every Ollama call) so OCR and grading never share VRAM.
Two-pass mode is on by default (`GLM_TWO_PASS=1`); disable it for max
throughput on big batches.

## Setup (Windows laptop)

```bat
cd glm-version
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

1. Install [Ollama](https://ollama.com), then pull the models:

```bash
ollama pull llama3.2:3b        # grading
ollama pull glm-ocr            # GLM-OCR (use the exact tag `ollama list` shows)
```

2. Start the service:

```bat
run.bat            :: or: python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

3. Open `http://localhost:8001` on the laptop, or from any phone on the same
   Wi-Fi use `http://<laptop-LAN-IP>:8001`. For remote/phone testing over the
   internet, tunnel it:

```bash
ssh -p 443 -R0:localhost:8001 free.pinggy.io
```

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

## GLM-OCR vs Chandra edition

| | This (GLM-OCR) | Chandra edition |
|---|---|---|
| OCR model | GLM-OCR 0.9B (tables + LaTeX strong, 0.9B = tiny VRAM) | Chandra OCR (Datalab) |
| Modes | Ollama local only | Ollama local **or** Datalab hosted API |
| Multi-pass | Built-in two-pass with high-accuracy retry | Single pass |
| Port | 8001 | 8000 |

Run both side by side on the same answer sheets and compare the
`results/*.json` outputs to pick the winner per subject.
