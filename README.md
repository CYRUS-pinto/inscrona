# Inscrona

AI-powered essay answer sheet grading tool. Upload handwritten answer sheets, get structured marks, feedback, and OCR transcripts.

## Prerequisites

- **Python 3.10+** (with pip)
- **Ollama** running locally at `http://127.0.0.1:11434`
- Two models pulled in Ollama:
  ```
  ollama pull glm-ocr
  ollama pull llama3.2:3b
  ```

## Quick Start

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Verify everything is ready (Ollama, models, directories)
python start.py --check-only

# 3. Launch the server
python start.py
```

Open **http://localhost:8000/** in your browser.

## Remote Phone Access (Pinggy)

To access the UI from your phone over HTTPS:

```bash
ssh -p 443 -R0:localhost:8000 free.pinggy.io
```

Copy the generated `https://*.free.pinggy.link` URL and open it in your phone's browser.

## Key Features

- **Image upload** — JPEG, PNG, HEIC (iPhone photos auto-converted)
- **Auto-resize** — Images >2000px on longest edge are downscaled before OCR
- **Sequential model execution** — GLM-OCR extracts text, then Llama 3.2:3b grades it. Models load/unload one at a time (zero VRAM leakage)
- **Collapsible OCR transcript** — Review the raw handwritten text extracted by GLM-OCR
- **Confidence badges** — Green (auto-accept ≥80%), Orange (review 60–79%), Red (manual <60%)
- **Past submissions** — Browse previously graded papers without re-running models
- **CSV export** — Download all grades as a spreadsheet for mark recording

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web upload UI |
| `/health` | GET | Health check (`{"status":"ok"}`) |
| `/grade` | POST | Grade an image (multipart `file` + `rubric` form fields) |
| `/results` | GET | List all past graded submissions |
| `/results/export.csv` | GET | Download grades as CSV |

## Project Structure

```
Inscrona/
├── main.py              # FastAPI application
├── start.py             # Launcher with pre-flight checks
├── requirements.txt     # Python dependencies
├── notion.design.md     # Design tokens (Notion-inspired)
├── templates/
│   └── index.html       # Web UI (served by FastAPI)
├── uploads/             # Saved uploaded images
└── results/             # Saved grading results (JSON)
```
