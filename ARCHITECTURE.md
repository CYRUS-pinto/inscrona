# Inscrona — Unified Architecture

> AI-powered answer-sheet correction engine. OCR handwritten answers, grade against answer key, score + feedback.

---

## Golden Rule

**Models run sequentially, never simultaneously.**

OCR model loads → extracts → unloads (keep_alive: 0) → grading LLM loads → evaluates → unloads. Consumer hardware (8–12GB VRAM) cannot hold two models in memory at once.

---

## Pipeline

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌────────────┐
│  PDF/Image   │────▶│  Preprocess  │────▶│  OCR (dual)  │────▶│ Structural │
│  Input       │     │  + Layout    │     │  Chandra GLM │     │ Analysis   │
└─────────────┘     └──────────────┘     └──────────────┘     └─────┬──────┘
                                                                     │
┌─────────────┐     ┌──────────────┐                                │
│  Score +     │◀────│   Grading    │◀───────────────────────────────┘
│  Feedback    │     │  2-pass QA   │
└─────────────┘     └──────────────┘
```

1. **Preprocess** — Page detection, deskew, denoise, contrast boost
2. **Layout** — Segment into regions: questions, answer boxes, margins, headers
3. **OCR** — Dual mode: Chandra (layout-engine) + GLM (vision model)
4. **Structural analysis** — Map OCR text to questions/marks via answer-key template
5. **Grading** — PASS1 (quick match) + PASS2 (quality check on weak pages)
6. **Output** — Per-question score, total, feedback, confidence, weak-page flag

---

## Directory Structure

```
inscrona/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, routes, startup/shutdown
│   ├── config.py            # Pydantic Settings: paths, model refs, timeouts
│   ├── schemas.py           # Pydantic models: Paper, Page, Question, GradeResult
│   │
│   ├── preprocess.py        # Page detection, deskew, denoise, contrast
│   ├── layout.py            # OpenCV contour-based region segmentation
│   │
│   ├── ocr.py               # Dual-mode OCR: Chandra (Ollama) + GLM (Ollama/API)
│   │   ├── chandra_ocr()   #   Layout-engine OCR (question labels, headers)
│   │   ├── glm_ocr()       #   Vision-model OCR (handwritten answer text)
│   │   └── _unload_model() #   keep_alive: 0 after each extraction
│   │
│   ├── grader.py            # Two-pass grading engine
│   │   ├── grade()          #   PASS1: quick keyword/structure match
│   │   └── grade_pass2()    #   PASS2: semantic quality check on weak pages
│   │
│   ├── answer_key.py        # Load + parse answer key templates (JSON/YAML/PDF)
│   ├── feedback.py          # Per-question feedback generator
│   ├── jobs.py              # Async job queue (subprocess, status, results)
│   └── audit.py             # Override logging, confidence tracking
│
├── api/
│   ├── __init__.py
│   ├── routes.py            # POST /api/grade, GET /api/job/{id}, GET /api/health
│   └── middleware.py        # CORS, error handler, request logging
│
├── models/
│   └── (ollama model files downloaded at setup)
│
├── samples/                 # Test answer sheets (real + fabricated)
├── qp/                      # Question papers / answer keys
├── output/                  # Grade results, audit logs, exports
├── tests/
│   ├── test_preprocess.py
│   ├── test_ocr.py
│   ├── test_grader.py
│   ├── test_integration.py  # End-to-end: sample → score
│   └── conftest.py
│
├── ARCHITECTURE.md          # This file
├── requirements.txt
└── run.py                   # Entry point: uvicorn app.main:app
```

---

## Module Responsibilities

### preprocess.py
- Input: raw page image (BGR numpy array)
- Output: processed page image
- Operations: page boundary detection (optional crop), deskew via Hough transform, denoise (cv2.fastNlMeansDenoising), contrast enhancement (CLAHE)
- No model calls

### layout.py
- Input: processed page image
- Output: list of `Region(x, y, w, h, region_type)` — question-area, answer-area, header, margin
- Algorithm: adaptive threshold → findContours → filter by aspect ratio + position → classify by vertical position (top = header, middle = Q-area, bottom = answer)
- No model calls
- Reuses OpenCV-based approach from both GLM and Chandra (identical code)

### ocr.py — Dual Mode

**Chandra mode** (default):
- Calls local Ollama API (`localhost:11434`) with layout-engine model
- Prompt: "Extract all text from this answer sheet region. Return JSON with question_number, answer_text, confidence."
- Handles structured answer sheets (Q1, Q2, Q3 format)
- keep_alive: 0 — model unloaded after each call

**GLM mode** (alternative):
- Calls local Ollama API (`localhost:8001`) with vision model (GLM-OCR or Qwen2-VL)
- Prompt: "Read all handwritten text in this image. Return raw text with line breaks."
- Handles dense handwritten pages where layout detection fails
- keep_alive: 0 — model unloaded after each call

**Fallback**: If Chandra OCR confidence < threshold, retry with GLM on weak pages only.

**Fallback (API mode)**: If Ollama unavailable, try Datalab API (Chandra's remote option).

### grader.py — Two-Pass

**PASS1** (Quick):
- Input: OCR text + answer key for that question
- Method: exact/semantic match against answer key, keyword extraction, structure verification
- Output: `GradeResult(score, max_score, confidence, feedback, needs_pass2)`

**PASS2** (Quality Check — weak pages only):
- Input: questions where PASS1 confidence < 0.7 or score < 50%
- Method: Re-grade with LLM using detailed prompt:
  ```
  "You are a university examiner. Grade this answer against the answer key.
   Provide: score, key_points_hit, missing_points, detailed feedback.
   Be strict but fair. Partial credit allowed."
  ```
- Output: updated `GradeResult` with higher confidence

### answer_key.py
- Input: answer key file (JSON, YAML, or PDF)
- Output: `AnswerKeyTemplate` — structured questions with expected answers, max marks, grading hints
- Formats:
  - JSON: `{"questions": [{"id": "Q1", "text": "...", "max_marks": 10, "key_points": [...]}]}`
  - YAML: same structure
  - PDF: OCR-extracted and mapped via question number pattern matching

### jobs.py
- Async job queue using asyncio + subprocess
- POST /api/grade → returns job_id immediately
- Background worker: preprocess → OCR → structural → grade → store result
- GET /api/job/{id} → returns status (queued/processing/completed/failed) + result when ready
- Job result stored in memory (dict) — SQLite later

---

## Config Schema (config.py)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ocr_model: str = "glm-ocr:latest"        # GLM vision model
    grading_model: str = "qwen2.5:7b"        # Grading LLM
    keep_alive: int = 0                       # Unload after each call

    # Chandra fallback
    datalab_api_url: str | None = None        # Remote Datalab API

    # Pipeline
    ocr_confidence_threshold: float = 0.7    # Below this → GLM retry
    pass2_confidence_threshold: float = 0.7  # Below this → PASS2 triggered
    max_retries: int = 2

    # Paths
    samples_dir: str = "samples"
    qp_dir: str = "qp"
    output_dir: str = "output"

    class Config:
        env_file = ".env"
```

---

## Schemas (schemas.py)

```python
from pydantic import BaseModel
from enum import Enum

class RegionType(str, Enum):
    HEADER = "header"
    QUESTION = "question"
    ANSWER = "answer"
    MARGIN = "margin"

class Region(BaseModel):
    x: int
    y: int
    w: int
    h: int
    region_type: RegionType

class Question(BaseModel):
    id: str                    # "Q1", "Q2a", etc.
    text: str                  # Question text from answer key
    max_marks: float
    key_points: list[str]      # Expected answer elements
    ocr_text: str = ""         # Extracted answer text
    regions: list[Region] = [] # Layout regions for this question

class GradeResult(BaseModel):
    question_id: str
    score: float
    max_score: float
    confidence: float          # 0.0 - 1.0
    feedback: str
    key_points_hit: list[str]
    missing_points: list[str]
    needs_pass2: bool = False
    pass2_applied: bool = False

class PaperResult(BaseModel):
    paper_id: str
    student_id: str = ""
    total_score: float
    max_total: float
    grades: list[GradeResult]
    processing_time_ms: float
    ocr_model_used: str
    pass2_pages: list[int] = []  # Page numbers that triggered PASS2

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Job(BaseModel):
    id: str
    status: JobStatus
    result: PaperResult | None = None
    error: str | None = None
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/health` | Model status, disk, uptime |
| `POST` | `/api/grade` | Submit answer sheet → returns `job_id` |
| `GET`  | `/api/job/{id}` | Poll job status + result |
| `POST` | `/api/grade/{id}/override` | Teacher score override (audit logged) |
| `GET`  | `/api/answer-key` | List loaded answer keys |
| `POST` | `/api/answer-key` | Upload new answer key |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| OCR mode | Dual (Chandra + GLM) | Chandra for structured sheets, GLM for dense handwriting |
| Model scheduling | Sequential with keep_alive: 0 | Consumer VRAM constraint (8-12GB) |
| Quality check | Two-pass (PASS1 + PASS2) | Catches grading errors on weak pages without full re-grade |
| Job queue | Async in-memory | Fast iteration; SQLite for persistence later |
| Answer key format | JSON/YAML/PDF | JSON/YAML for dev, PDF for real teacher use |
| Preprocessing | OpenCV only | No model needed, fast, deterministic |
| Layout detection | OpenCV contours | Proven in both GLM and Chandra editions |

---

## Tech Stack

- **Runtime**: Python 3.11+
- **API**: FastAPI + uvicorn
- **OCR**: Ollama (local) with Chandra (layout-engine) + GLM (vision) models
- **Fallback API**: Datalab API (Chandra's remote option)
- **Grading LLM**: Ollama with Qwen 2.5 7B (or similar)
- **Image processing**: OpenCV, Pillow, NumPy
- **Schemas**: Pydantic v2
- **Testing**: pytest + httpx
- **Error tracking**: Sentry (planned)
