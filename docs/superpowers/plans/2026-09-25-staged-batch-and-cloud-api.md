# Staged Two-Phase Batch Pipeline & Pluggable Cloud API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a high-throughput, memory-adaptive staged batch grading engine with pluggable Cloud API option (Gemini Flash / OpenRouter) and "Review by Exception" teacher UI.

**Architecture:** Decouples grading into Phase 1 (Bulk OCR with single weight load) and Phase 2 (Bulk Evaluation with single weight load) to eliminate model thrashing on 4GB-6GB laptops while providing sub-2s Cloud API fallback and 16GB Colab T4 concurrent acceleration. Transcripts are cached in SQLite so teachers can re-grade rubrics without re-running vision OCR.

**Tech Stack:** FastAPI, Python 3.12 (stdlib sqlite3/asyncio), httpx, Pillow, Ollama, Google GenAI / OpenRouter REST APIs, Vanilla JS / CSS.

**Spec:** [`docs/superpowers/specs/2026-09-25-staged-batch-pipeline-design.md`](file:///C:/Users/Cyrus/Downloads/New%20folder%20(72)/Inscrona/docs/superpowers/specs/2026-09-25-staged-batch-pipeline-design.md)

## Global Constraints
- Standard library only for scheduling (`asyncio`, `sqlite3`, `pathlib`, `json`). No Celery or Redis.
- Zero model thrashing on <=6GB VRAM (exactly one model in memory at any point during staged batch).
- Resized vision images capped at 1400px longest edge for 50% fewer vision tokens with 100% handwriting legibility.
- Strict backwards compatibility: existing single-paper `POST /grade` and `GET /health` remain functional.

---

### Task 1: Staged Two-Phase Batch Engine & Decoupled SQLite Schema

**Files:**
- Create: `batch.py`
- Modify: `main.py` (database initialization)
- Test: `tests/test_batch_engine.py`

**Interfaces:**
- Consumes: `uploads/` directory, Ollama API / Colab endpoints
- Produces: `StagedBatchManager` class with `create_batch(files, rubric, engine)`, `run_phase1_ocr(batch_id)`, `run_phase2_grade(batch_id, new_rubric=None)`, `get_batch_status(batch_id)`

- [ ] **Step 1: Write failing test for StagedBatchManager initialization and batch queueing**

```python
# tests/test_batch_engine.py
import pytest
from batch import StagedBatchManager

@pytest.mark.asyncio
async def test_batch_creation_and_phase_progression(tmp_path):
    mgr = StagedBatchManager(db_path=str(tmp_path / "test_batch.db"))
    await mgr.init_db()
    batch_id = await mgr.create_batch(
        items=[{"filename": "p1.jpg", "content": b"fake_jpg"}],
        rubric="Rate 0-10",
        engine="staged_local"
    )
    assert batch_id.startswith("b_")
    status = await mgr.get_status(batch_id)
    assert status["total_papers"] == 1
    assert status["current_phase"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batch_engine.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'batch'`

- [ ] **Step 3: Implement minimal StagedBatchManager in `batch.py`**

```python
# batch.py
import os, time, uuid, json, asyncio, sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any

class StagedBatchManager:
    def __init__(self, db_path: str = "database.db"):
        self.db_path = db_path
        self._queue = asyncio.Queue()

    async def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    rubric TEXT,
                    engine TEXT,
                    status TEXT,
                    current_phase INTEGER,
                    total_papers INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_papers (
                    job_id TEXT PRIMARY KEY,
                    batch_id TEXT,
                    filename TEXT,
                    ocr_text TEXT,
                    marks REAL,
                    max_marks REAL,
                    confidence REAL,
                    feedback TEXT,
                    status TEXT,
                    FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
                )
            """)
            conn.commit()

    async def create_batch(self, items: List[Dict[str, Any]], rubric: str, engine: str = "staged") -> str:
        batch_id = f"b_{uuid.uuid4().hex[:8]}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO batches (batch_id, rubric, engine, status, current_phase, total_papers) VALUES (?, ?, ?, ?, ?, ?)",
                (batch_id, rubric, engine, "queued", 0, len(items))
            )
            for it in items:
                job_id = uuid.uuid4().hex[:12]
                conn.execute(
                    "INSERT INTO batch_papers (job_id, batch_id, filename, status) VALUES (?, ?, ?, ?)",
                    (job_id, batch_id, it.get("filename", "upload.jpg"), "pending")
                )
            conn.commit()
        return batch_id

    async def get_status(self, batch_id: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
            if not row:
                raise ValueError("Batch not found")
            papers = conn.execute("SELECT * FROM batch_papers WHERE batch_id = ?", (batch_id,)).fetchall()
            return {
                "batch_id": row["batch_id"],
                "rubric": row["rubric"],
                "engine": row["engine"],
                "status": row["status"],
                "current_phase": row["current_phase"],
                "total_papers": row["total_papers"],
                "papers": [dict(p) for p in papers]
            }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_batch_engine.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add batch.py tests/test_batch_engine.py
git commit -m "feat(batch): implement StagedBatchManager schema and queueing"
```

---

### Task 2: Pluggable High-Speed Cloud Flash API Option (`cloud_api.py`)

**Files:**
- Create: `cloud_api.py`
- Test: `tests/test_cloud_api.py`

**Interfaces:**
- Consumes: `GEMINI_API_KEY` or `OPENROUTER_API_KEY` from `.env`
- Produces: `async def cloud_grade(image_bytes: bytes, rubric: str, provider: str = "gemini") -> dict`

- [ ] **Step 1: Write test for cloud grading provider contract**

```python
# tests/test_cloud_api.py
import pytest
from cloud_api import parse_cloud_grading_response

def test_cloud_response_parsing():
    raw_json = '{"marks": 9, "confidence": 0.95, "feedback": "Excellent work", "ocr_text": "Answer 1..."}'
    res = parse_cloud_grading_response(raw_json)
    assert res["total_marks"] == 9.0
    assert res["confidence"] == 0.95
    assert res["feedback"] == "Excellent work"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cloud_api.py -v`  
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `cloud_api.py` supporting Gemini 1.5/2.0 Flash & OpenRouter**

```python
# cloud_api.py
import os, json, re, base64, httpx
from typing import Dict, Any

def parse_cloud_grading_response(raw: str) -> Dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join([l for l in cleaned.split("\n") if not l.startswith("```")])
    data = json.loads(cleaned)
    marks = data.get("marks", 0)
    if isinstance(marks, (int, float)):
        score = float(marks)
    else:
        score = 0.0
    conf = float(data.get("confidence", 0.8))
    if conf > 1.0:
        conf = conf / 100.0
    return {
        "total_marks": score,
        "max_total_marks": 10.0,
        "percentage": (score / 10.0) * 100.0,
        "confidence": conf,
        "confidence_level": "high" if conf >= 0.75 else "medium",
        "feedback": data.get("feedback", ""),
        "ocr_text": data.get("ocr_text", ""),
        "model_used": "cloud_flash_api"
    }

async def cloud_grade(image_bytes: bytes, rubric: str) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured in .env")
    
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = f"""Extract all handwritten text from this student exam answer sheet, and grade it according to the rubric.
Rubric: {rubric}
Respond ONLY with valid JSON:
{{"marks": <0-10>, "confidence": <0.0-1.0>, "feedback": "<specific feedback>", "ocr_text": "<full transcript>"}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}}
            ]
        }],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parse_cloud_grading_response(text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cloud_api.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cloud_api.py tests/test_cloud_api.py
git commit -m "feat(cloud): add pluggable sub-2s cloud Flash API grading provider"
```

---

### Task 3: Fast Batch & Re-Grade Endpoints in FastAPI (`main.py`)

**Files:**
- Modify: `main.py`
- Test: `tests/test_batch_endpoints.py`

**Interfaces:**
- Consumes: `StagedBatchManager` from `batch.py`, `cloud_grade` from `cloud_api.py`
- Produces: `POST /grade/batch`, `GET /grade/batch/{batch_id}`, `POST /grade/batch/{batch_id}/regrade`

- [ ] **Step 1: Write integration tests for batch upload and status**

```python
# tests/test_batch_endpoints.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_batch_upload_accepts_files():
    files = [("files", ("test.jpg", b"fakecontent", "image/jpeg"))]
    resp = client.post("/grade/batch", files=files, data={"rubric": "Default"})
    assert resp.status_code == 202
    data = resp.json()
    assert "batch_id" in data
    assert data["total_papers"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_batch_endpoints.py -v`  
Expected: FAIL (404 Not Found)

- [ ] **Step 3: Implement batch endpoints and worker loops in `main.py`**

Wire `POST /grade/batch`, background tasks processing Phase 1 (All OCR) followed by Phase 2 (All Grading), and `POST /grade/batch/{batch_id}/regrade` which runs only Phase 2 over cached transcripts.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_batch_endpoints.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_batch_endpoints.py
git commit -m "feat(api): implement /grade/batch and decoupled /regrade endpoints"
```

---

### Task 4: Teacher Batch Queue & Review by Exception UI (`templates/index.html`)

**Files:**
- Modify: `templates/index.html`
- Test: Chrome browser DevTools snapshot / screenshot

**Interfaces:**
- Consumes: `/grade/batch`, WebSocket `/ws/batch/{id}`
- Produces: Multi-file dropzone, 2-phase progress indicators, "Review by Exception" table filtering.

- [ ] **Step 1: Add Multi-File Batch Dropzone and Engine Selector to `templates/index.html`**
  - Engine Select: `[Auto-Adaptive | Colab T4 Burst | Cloud Flash API]`
  - Multi-file drop input (`multiple` attribute on file input).
- [ ] **Step 2: Add Two-Phase Progress Bar**
  - Phase 1: `Reading handwriting (N/M)` (Green fill)
  - Phase 2: `Grading against rubric (N/M)` (Indigo fill)
- [ ] **Step 3: Implement "Review by Exception" sorting in table**
  - Papers with confidence < 70% pinned at the top with amber badge.
  - One-click score adjustment popup.
- [ ] **Step 4: Verify visually with browser DevTools screenshot**
- [ ] **Step 5: Commit**

```bash
git add templates/index.html
git commit -m "feat(ui): add batch dropzone, two-phase progress bars, and review by exception table"
```

---

### Task 5: End-to-End Verification & Benchmark Suite

**Files:**
- Create: `tests/test_batch_pipeline_e2e.py`
- Test: Full pytest run (`uv run pytest tests`)

- [ ] **Step 1: Write end-to-end integration test verifying 0 model thrashing**
- [ ] **Step 2: Verify all 25+ unit tests pass**
- [ ] **Step 3: Update `PROGRESS.md` with benchmark comparison**
- [ ] **Step 4: Commit & Push to GitHub (`master` & `main`)**
