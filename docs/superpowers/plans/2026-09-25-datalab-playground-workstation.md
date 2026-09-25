# Datalab-Style Playground Workstation & Universal Hardware Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Inscrona Playground into a Datalab-style split-screen document evaluation workstation adhering strictly to `notion.design.md`, with universal hardware acceleration (Mac Metal, Nvidia CUDA, Colab T4, Sub-2s Cloud).

**Architecture:** Dual-pane document workspace (left: high-res scanned exam sheet with interactive color-coded question bounding boxes; right: Datalab-style multi-tab inspector with Marks, Blocks, Markdown, JSON, and bidirectional hover linking). Backed by a universal hardware dispatcher optimizing for Mac Apple Silicon, Nvidia GPUs, Colab, and CPU laptops.

**Tech Stack:** FastAPI, Python 3.12, Vanilla JS / CSS (`notion.design.md` design tokens), Pillow, Ollama, Mistral/Gemini APIs.

**Spec:** [`docs/superpowers/specs/2026-09-25-datalab-playground-workstation.md`](file:///c:/Users/Cyrus/Downloads/New%20folder%20(72)/Inscrona/docs/superpowers/specs/2026-09-25-datalab-playground-workstation.md)

## Global Constraints
- Strictly follow [`notion.design.md`](file:///c:/Users/Cyrus/Downloads/New%20folder%20(72)/Inscrona/notion.design.md): Brand navy `#0a1530`, signature purple CTA `#5645d4`, pastel card tints (`#e6e0f5`, `#fde0ec`, `#dcecfa`, `#d9f3e1`, `#ffe8d4`), rectangular 8px buttons, 12px cards.
- Zero dependencies added (stdlib Python, native browser DOM/CSS).
- Universal hardware support: Mac M1-M4 Metal, Windows/Linux CUDA, CPU Two-Phase Staged.
- Backwards compatibility: All existing single and batch endpoints remain 100% operational.

---

### Task 1: Bounding Box & Document Block Model in Backend

**Files:**
- Create: `blocks.py`
- Modify: `main.py`
- Test: `tests/test_block_coordinates.py`

**Interfaces:**
- Consumes: OCR transcripts, question breakdowns
- Produces: `extract_document_blocks(ocr_text, question_grades, img_width, img_height) -> List[Dict]` with normalized `box_2d: [ymin, xmin, ymax, xmax]` and block types (`PAGEHEADER`, `QUESTION`, `HANDWRITING`, `DIAGRAM`).

- [ ] **Step 1: Write failing test for document block extraction**

```python
# tests/test_block_coordinates.py
from blocks import extract_document_blocks

def test_extract_document_blocks():
    ocr_text = "INTERNAL ASSESSMENT\\nQ1: Photosynthesis definition\\nAns: Green plants convert CO2\\nQ2: Explain recursion"
    q_grades = [
        {"question_id": "Q1", "marks_awarded": 4.0, "max_marks": 5.0, "feedback": "Good"},
        {"question_id": "Q2", "marks_awarded": 3.5, "max_marks": 5.0, "feedback": "Clear"}
    ]
    blocks = extract_document_blocks(ocr_text, q_grades)
    assert len(blocks) >= 3
    assert blocks[0]["type"] == "PAGEHEADER"
    assert any(b["type"] == "QUESTION" and b.get("question_id") == "Q1" for b in blocks)
    assert all("box_2d" in b for b in blocks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_block_coordinates.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'blocks'`

- [ ] **Step 3: Implement `blocks.py`**

Create `blocks.py` with intelligent layout parsing and normalized coordinate generation.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_block_coordinates.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add blocks.py tests/test_block_coordinates.py
git commit -m "feat(blocks): implement layout block extraction and normalized bounding box mapping"
```

---

### Task 2: Hardware-Adaptive Auto-Detector & Universal Dispatcher

**Files:**
- Create: `hardware.py`
- Modify: `main.py`
- Test: `tests/test_hardware_dispatch.py`

**Interfaces:**
- Produces: `detect_hardware() -> Dict[str, Any]` returning `{"platform": "darwin|win32|linux", "gpu_type": "apple_metal|nvidia_cuda|cpu", "recommended_engine": "..."}`.

- [ ] **Step 1: Write failing test for hardware detection**

```python
# tests/test_hardware_dispatch.py
from hardware import detect_hardware

def test_detect_hardware():
    hw = detect_hardware()
    assert "platform" in hw
    assert "gpu_type" in hw
    assert "recommended_engine" in hw
    assert hw["gpu_type"] in {"apple_metal", "nvidia_cuda", "cpu"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hardware_dispatch.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'hardware'`

- [ ] **Step 3: Implement `hardware.py`**

Detects Apple Silicon Metal on macOS, Nvidia CUDA via nvml/smi on Windows/Linux, and provides optimal context/thread settings.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hardware_dispatch.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hardware.py tests/test_hardware_dispatch.py
git commit -m "feat(hardware): implement hardware-adaptive engine detection for Mac Metal and Nvidia CUDA"
```

---

### Task 3: Dual-Pane Visual Workstation & Notion Design System (`templates/index.html`)

**Files:**
- Modify: `templates/index.html`
- Test: Live browser DevTools snapshot / screenshot

**Interfaces:**
- Consumes: `/results/{job_id}` returning image URL, `blocks`, `question_grades`, `ocr_text`.
- Produces: Dual-pane layout in `#paneInspector`:
  - Left Canvas: Image viewer with zoom controls, bounding boxes with Notion pastel tints (`#e6e0f5`, `#fde0ec`, `#dcecfa`, `#d9f3e1`).
  - Right Multi-Tab Inspector: `[ 📝 Marks | 🧱 Blocks | 📄 Markdown | ⚙️ JSON ]`.
  - Bidirectional click & hover highlighting.

- [ ] **Step 1: Implement Notion design system tokens and split-screen grid in CSS**
- [ ] **Step 2: Implement Left Document Canvas with interactive SVG bounding boxes and zoom**
- [ ] **Step 3: Implement Right Datalab-Style Multi-Tab Navigation (`Marks`, `Blocks`, `Markdown`, `JSON`)**
- [ ] **Step 4: Wire bidirectional hover and click events between bounding boxes and block cards**
- [ ] **Step 5: Verify visually via browser screenshot**
- [ ] **Step 6: Commit**

```bash
git add templates/index.html
git commit -m "feat(ui): implement Datalab split-screen document workstation adhering to notion.design.md"
```

---

### Task 4: Full Suite Verification & Push

**Files:**
- Run full pytest test suite (`pytest tests/`)
- Update `PROGRESS.md`
- Push to GitHub `master` & `main`

- [ ] **Step 1: Run all unit and integration tests**
- [ ] **Step 2: Verify live grading on `test_sheet_1.jpg`**
- [ ] **Step 3: Update `PROGRESS.md`**
- [ ] **Step 4: Commit & push to `master` and `main`**
