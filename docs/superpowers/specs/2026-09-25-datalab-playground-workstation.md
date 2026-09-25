# Datalab-Style Document Inspection Workstation & Universal Hardware Spec

> **Specification**: Dual-Pane Visual Document Workstation adhering to `notion.design.md` with Universal Hardware Inference (Mac Apple Silicon Metal, Windows/Linux Nvidia CUDA, Colab T4 GPU, Sub-2s Cloud API).

## 1. Executive Summary & Goal
Transform the Inscrona Grading Playground from a simple linear list into a **professional dual-pane document evaluation workstation** inspired by the Datalab document playground (`datalab.to/playground`), strictly following the design system tokens in [`notion.design.md`](file:///c:/Users/Cyrus/Downloads/New%20folder%20(72)/Inscrona/notion.design.md).

Teachers get:
1. **Left Canvas (Document View)**: High-resolution scanned answer sheet with color-coded, interactive bounding boxes overlaid over detected questions (`Q1`, `Q2`, `Q3`), headers, and student handwriting with pan/zoom controls.
2. **Right Canvas (Datalab Multi-Tab Inspector)**:
   - `[ 📝 Marks & Rubric | 🧱 Blocks | 📄 Markdown | ⚙️ JSON ]`
   - Real-time bidirectional linking: Clicking or hovering on "Question 1" highlights and scrolls to the exact handwriting snippet on the left.
3. **Universal Hardware Acceleration**:
   - **Mac (Apple Silicon M1/M2/M3/M4)**: Auto-detects macOS and leverages native Apple Metal (MPS) Unified Memory for 60+ tokens/sec local grading.
   - **Windows / Linux (Nvidia CUDA)**: Auto-offloads 100% of layers to Nvidia RTX/GTX GPUs via `num_gpu: 99`.
   - **Colab Tesla T4 GPU (Free)**: Zero-load 16GB VRAM remote burst via Cloudflare Tunnel.
   - **Cloud Tier (Mistral Pixtral 12B / Gemini 2.0 Flash)**: Sub-2s latency, ~$0.0001/paper cost, 98.5% handwriting accuracy.

---

## 2. Design System Alignment (`notion.design.md`)

* **Color Palette**:
  - Topbar & Hero Band: Brand Navy `#0a1530`
  - Primary Action / CTA: Signature Purple `#5645d4` (pressed `#4534b3`, disabled `#e5e3df`)
  - Canvas: `#ffffff`, Surface: `#f6f5f4`, Surface Soft: `#fafaf9`
  - Hairlines: Border `#e5e3df`, Strong Border `#c8c4be`
  - Text: Ink Deep `#000000`, Ink `#1a1a1a`, Charcoal `#37352f`, Slate `#5d5b54`, Muted `#bbb8b1`
  - Pastel Block Tints (matching Notion DB properties & Datalab blocks):
    - `PAGEHEADER`: Lavender tint (`#e6e0f5`, text `#391c57`)
    - `SECTIONHEADER`: Rose tint (`#fde0ec`, text `#a02e6d`)
    - `QUESTION`: Sky tint (`#dcecfa`, text `#005bab`)
    - `HANDWRITING`: Mint tint (`#d9f3e1`, text `#1aae39`)
    - `DIAGRAM / FORMULA`: Peach tint (`#ffe8d4`, text `#793400`)
    - `NEEDS REVIEW (<70%)`: Bold Yellow tint (`#f9e79f`, text `#523410`)
* **Shape Language**:
  - Rectangular 8px buttons (`rounded: 8px`), never generic pill buttons
  - Cards & Panels: 12px radius (`rounded: 12px`) with subtle 1px hairline border (`#e5e3df`)
  - Status Badges & Chips: Pill-shaped (`rounded: 9999px`)
* **Typography**:
  - Notion Sans / Inter font hierarchy (`Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
  - Data / Job IDs / Code: `JetBrains Mono`

---

## 3. UI Component Architecture

### 3.1 Split-Screen Inspector Layout (`#paneInspector`)
```
+--------------------------------------------------------------------------------------------------+
| Topbar: Brand Navy #0a1530 | Inscrona Grading Playground | [MODE: Hybrid] | [Export CSV]         |
+--------------------------------------------------------------------------------------------------+
| LEFT: PAPERS QUEUE (300px)   | CENTER-RIGHT: DUAL-PANE WORKSTATION (Split 50/50)                 |
| ---------------------------- | ----------------------------------------------------------------- |
| • Filters:                   | [DOCUMENT VIEWER]                 | [DATALAB MULTI-TAB INSPECTOR] |
|   [All | ⚠️ Review | High]   | • High-res exam sheet             | Tabs:                         |
| • Papers list:               | • Overlaid bounding boxes:        | [ 📝 Marks | 🧱 Blocks |     |
|   #5f5220 - 80% (High)       |   - Q1 [rgba(0,117,222,0.12)]     |   📄 Markdown | ⚙️ JSON ]     |
|   #de65ef - 62% (⚠️ Review)  |   - Q2 [rgba(26,174,57,0.12)]     | • Marks Tab:                  |
|   #05980f - 95% (High)       |   - Diagram [rgba(221,91,0,0.12)] |   Donut score, Q breakdown,   |
|                              | • Controls: [Zoom + / - / Reset]  |   criteria meters, flags.     |
|                              |   [Toggle Boxes]                  | • Blocks Tab:                 |
|                              | • Interactive sync: Click on box  |   Datalab-style colored chips |
|                              |   scrolls to question card!       | • Markdown Tab: Clean text.   |
+--------------------------------------------------------------------------------------------------+
```

### 3.2 Bounding Box & Coordinate Model
When grading an answer sheet (either via Local GLM/Chandra or Cloud Pixtral/Gemini):
* Each question detected (`Q1`, `Q2`, etc.) has estimated or detected bounding box normalized coordinates:
  `{"id": "Q1", "box_2d": [ymin, xmin, ymax, xmax], "type": "QUESTION", "marks": 4.0, "max_marks": 5.0}`
* The frontend scales normalized coordinates `[0, 1000]` to the rendered image width and height using SVG overlay or absolute CSS positioning.
* Clicking on any bounding box on the image selects and highlights the corresponding card on the right; hovering over the card on the right pulses the box on the image.

---

## 4. Universal Hardware Engine Abstraction

The backend will expose an explicit hardware-adaptive dispatch strategy:

```
                          ┌──────────────────────────┐
                          │   Inference Dispatcher   │
                          └─────────────┬────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                             ▼
┌──────────────────┐          ┌───────────────────┐         ┌────────────────────┐
│   Cloud Flash    │          │  Colab T4 Burst   │         │    Local Engine    │
│ (Pixtral/Gemini) │          │  (Free 16GB VRAM) │         │ (Zero-Thrashing)   │
├──────────────────┤          ├───────────────────┤         ├────────────────────┤
│ • ~1.5s - 2.5s   │          │ • ~25s - 30s      │         │ Auto-detected:     │
│ • ~$0.0001/paper │          │ • 100% Free Cloud │         │ • Mac M1-M4: Metal │
│ • SOTA Accuracy  │          │ • Zero Local Load │         │ • Windows/Linux:   │
│ • No GPU needed  │          │ • 16GB VRAM       │         │   CUDA / Staged CPU│
└──────────────────┘          └───────────────────┘         └────────────────────┘
```

1. **Mac (Apple Silicon)**:
   - In macOS environments, Ollama communicates directly with Metal (`libmetal`).
   - Context window optimized for unified memory without swapping.
2. **Nvidia Windows / Linux**:
   - `OLLAMA_NUM_GPU=99` offloads all layers to CUDA cores.
3. **Consumer CPU Laptop**:
   - Runs Two-Phase Staged batching ($O(1)$ model loads) so memory never thrashes.
   - 1-click burst to Colab or Cloud.

---

## 5. Verification Plan
* **Unit Tests**:
  - Test bounding box normalization and block schema extraction.
  - Test hardware engine selection matrix on macOS/Linux/Windows mocks.
  - Full suite passes (`uv run pytest tests`).
* **Visual & DevTools Verification**:
  - Inspect split-screen workstation with live student exam sheet (`test_sheet_1.jpg`).
  - Verify zoom/pan and bidirectional click/hover highlighting between canvas and inspector tabs.
  - Verify adherence to `notion.design.md` color tokens and 8px button geometry.
