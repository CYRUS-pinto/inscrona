# Staged Two-Phase Batch Pipeline & Memory-Adaptive Inference Architecture

**Date**: 2026-09-25  
**Status**: Approved (Brainstorming Complete)  
**Author**: Systems & Inference Architecture (Inscrona Team)

---

## 1. Executive Summary & Motivation

Inscrona grades handwritten student answer booklets using a two-model sequential AI pipeline:
1. **GLM-OCR** (0.9B parameters, vision-language model for handwriting transcription)
2. **Llama 3.2:3B** (3.2B parameters, instruction-tuned LLM for rubric assessment)

In real-world educational deployment, teachers grade batches of **30 to 80 exam papers** simultaneously. Standard sequential execution (`[Load M1] -> OCR -> [Unload M1] -> [Load M2] -> Grade -> [Unload M2]`) induces massive **model swapping penalties** on consumer hardware (4GB–6GB laptops), where swapping weights between VRAM and system memory wastes 5–10 seconds per paper (up to 5+ minutes of idle latency across a class set).

This specification designs a **Memory-Adaptive Staged Batch Pipeline**:
- **Staged Execution ($O(1)$ Weight Loads)**: Loads GLM-OCR once to transcribe all papers in bulk, then unloads it and loads Llama 3.2:3B once to evaluate all transcripts.
- **Adaptive Hardware Tiering**: Automatically detects available VRAM (laptop GPU vs. 16GB Colab T4 vs. CPU) to toggle between *Staged Batch Mode* (low VRAM) and *Concurrent Fast-Lane* (high VRAM).
- **Decoupled OCR Caching**: Stores raw transcripts independently, enabling teachers to adjust rubrics or re-grade without re-running expensive vision inference.
- **Live WebSocket Progress**: Emits granular two-phase progress updates to the frontend for zero perceived idle time.

---

## 2. Hardware Tiering & Adaptive Scheduling

The system detects local or remote GPU VRAM during startup and task scheduling:

```
                          ┌───────────────────────┐
                          │ Detect Available VRAM │
                          └───────────┬───────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
      VRAM >= 8 GB (e.g. T4 16GB,               VRAM < 8 GB (e.g. 4-6GB Laptop,
        RTX 3090/4090, A100)                     CPU / Shared Server)
                 │                                         │
                 ▼                                         ▼
     [Concurrent Fast-Lane]                    [Staged Two-Phase Batch]
  • Both models stay resident in VRAM       • Phase 1: GLM-OCR resident (~1.8GB)
  • Single-paper latency: 8-12s             • Transcribe N papers -> Save DB
  • Zero load/unload overhead               • Phase 2: Llama 3.2 resident (~2.2GB)
                                            • Grade N papers against rubric
                                            • Zero OOM risk on 4GB GPUs
```

### Hardware Specifications Matrix

| Environment | VRAM / RAM | Mode Selected | Max Resident Models | Expected 30-Paper Throughput |
| :--- | :--- | :--- | :--- | :--- |
| **Consumer Laptop** (RTX 3050/4050, 4–6GB VRAM) | 4–6 GB VRAM | **Staged Two-Phase** | 1 model | ~4.5 min (9s / sheet) |
| **Apple Silicon Mac** (M1/M2/M3 Unified 8–16GB) | Unified Memory | **Staged Two-Phase** | 1 model | ~5 min (10s / sheet) |
| **Cloud GPU Burst** (Google Colab T4, 15.3GB) | 15.3 GB VRAM | **Concurrent Fast-Lane** | 2 models | ~3.5 min (7s / sheet) |
| **Pro Server / Cloud** (A100 40GB, RTX 4090 24GB) | 24–40 GB VRAM | **Concurrent Batched** | 2 models (Parallel=4) | ~1.2 min (2.4s / sheet) |
| **Local CPU Fallback** (Office PC, 16GB RAM) | System RAM | **Staged Two-Phase** | 1 model (INT4) | Overnight / Background |

---

## 3. Staged Pipeline Execution Flow

```
Teacher Upload: [Drop 30 Images]
       │
       ▼
[POST /grade/batch] ──> Enqueues Batch ID into SQLite & asyncio.Queue
       │
       ├──────────────────────────────────────────────────────────────────┐
       ▼                                                                  ▼
[PHASE 1: BATCH TRANSCRIPTION]                             [PHASE 2: BATCH EVALUATION]
1. Load GLM-OCR (0.9B) into VRAM                            1. Load Llama 3.2 (3B) into VRAM
2. Resize all images to 1400px longest edge                 2. For each transcript in Batch:
3. For image in Batch:                                         • Construct Prompt with Rubric
   • Ollama generate (glm-ocr)                                 • Ollama generate (llama3.2:3b, json)
   • Save `ocr_text` to DB                                     • Calculate score, confidence, feedback
   • Broadcast WS: `{"phase": 1, "done": i, "total": N}`       • Save final grade to DB
4. Explicitly unload GLM-OCR (`keep_alive: 0`)                 • Broadcast WS: `{"phase": 2, "done": j, "total": N}`
                                                            3. Explicitly unload Llama 3.2 (`keep_alive: 0`)
                                                            4. Batch Complete -> Broadcast Summary
```

---

## 4. API Endpoints & Data Contracts

### 4.1 Batch Submission
- **Route**: `POST /grade/batch`
- **Form Data**:
  - `files`: List of `UploadFile` (Images: JPG, PNG, WebP, HEIC; or single ZIP archive)
  - `rubric`: String (Optional, defaults to accuracy/completeness/clarity rubric)
  - `burst`: Boolean (True = offload to Colab GPU; False = process on local host)
- **Response**: `202 Accepted`
  ```json
  {
    "batch_id": "b_7f8a91c2",
    "total_papers": 30,
    "status": "queued",
    "estimated_seconds": 240,
    "phase": "pending"
  }
  ```

### 4.2 Batch Status & Progress
- **Route**: `GET /grade/batch/{batch_id}`
- **Response**:
  ```json
  {
    "batch_id": "b_7f8a91c2",
    "status": "processing",
    "current_phase": 1,
    "phase_name": "transcription",
    "progress": {
      "phase1_completed": 18,
      "phase1_total": 30,
      "phase2_completed": 0,
      "phase2_total": 30
    },
    "papers": [
      {
        "job_id": "p_01",
        "filename": "sheet_1.jpg",
        "ocr_done": true,
        "graded": false,
        "score": null,
        "confidence": null
      }
    ]
  }
  ```

### 4.3 WebSocket Streaming Channel
- **Route**: `WS /ws/batch/{batch_id}`
- **Events Emitted**:
  - `phase_start`: `{"phase": 1, "model": "glm-ocr", "total": 30}`
  - `paper_ocr_done`: `{"job_id": "p_01", "ocr_chars": 642, "completed": 1, "total": 30}`
  - `phase_transition`: `{"unloaded": "glm-ocr", "loading": "llama3.2:3b"}`
  - `paper_graded`: `{"job_id": "p_01", "marks": 8.0, "max": 10.0, "confidence": 0.82}`
  - `batch_completed`: `{"batch_id": "b_7f8a91c2", "total_graded": 30, "flagged_count": 3}`

---

## 5. UI/UX Design: "Review by Exception"

Teachers do not inspect 30 identical high-scoring papers; they focus on edge cases:

1. **Dual Progress Bar**:
   - **Top Bar**: `Phase 1: Transcribing handwriting` (Green fill, 0–100%)
   - **Bottom Bar**: `Phase 2: Grading against rubric` (Indigo fill, 0–100%)
2. **Review Table with Smart Filtering**:
   - **Auto-Passed (Confidence ≥ 80%)**: Displayed with green badge; ready for one-click bulk export.
   - **Flagged for Review (Confidence < 70% or unreadable OCR)**: Pinned at the top with amber/red alert pill. Teacher clicks to view side-by-side image comparison with editable score input.
3. **Decoupled Rubric Re-grading**:
   - Button: `Re-grade Batch with New Rubric`.
   - Bypasses Phase 1 completely; uses cached transcripts from SQLite to re-run only Phase 2 in under 60 seconds for the entire class.

---

## 6. Implementation Stages & Acceptance Criteria

1. **Stage 1 (Backend Scheduler & Endpoints)**:
   - Add `POST /grade/batch` and `GET /grade/batch/{batch_id}` in `main.py`.
   - Implement `StagedBatchManager` with decoupled Phase 1 and Phase 2 loops.
   - Add VRAM detector to select Staged vs Concurrent strategy.
2. **Stage 2 (Colab Remote Runner Parity)**:
   - Update Colab remote inference daemon to expose `/ocr` and `/eval` endpoints for decoupled batch calling.
3. **Stage 3 (Frontend Multi-Drop & Batch Queue UI)**:
   - Enhance `templates/index.html` with multi-file dropzone, phase status indicators, and review table.
4. **Stage 4 (Verification & Unit Tests)**:
   - Add unit tests verifying 0 model thrashing, batch status reporting, and rubric re-evaluations.
