# TDD Evidence Report: Inscora Playground Website & Teacher UI Verification

## 1. Source Plan & Objectives
- **Plan Reference**: [implementation_plan.md](file:///C:/Users/Cyrus/.gemini/antigravity-ide/brain/cf23168f-5593-4dd4-8969-ca5ecdd1f577/implementation_plan.md)
- **PRD Reference**: [inscora-exam-engine.prd.md](file:///C:/Users/Cyrus/.gemini/antigravity-ide/brain/cf23168f-5593-4dd4-8969-ca5ecdd1f577/inscora-exam-engine.prd.md)
- **Scope**: Comprehensive verification of Playground Website HTML structure, CSS design tokens, KaTeX mathematical typography, Datalab-style bounding boxes, and teacher batch review queue with keyboard shortcuts.

---

## 2. User Journeys Tested

1. **Journey 1 (Semantic HTML & Layout)**:
   - *As a college lecturer*, I want the playground website to render clean semantic HTML with document metadata, responsive layout containers, and all real exam sample pills, so that I can inspect real student handwriting sheets seamlessly on desktop and mobile.
2. **Journey 2 (CSS Design Tokens & Theme)**:
   - *As a college lecturer*, I want dark obsidian/navy styling (`#090d16`, `#111726`), Datalab official semantic color tokens (`#9b51e0`, `#2563eb`, `#059669`, `#dc2626`), and non-occluding bounding box hovers, so that the UI looks editorial and never obscures student handwriting.
3. **Journey 3 (KaTeX Mathematical Equations)**:
   - *As a college lecturer evaluating STEM exams*, I want mathematical equations ($V_{out} = \sqrt{2}V_{rms}$, $\int x dx$) in student transcripts, rubric criteria, and grading evidence to render via KaTeX with standard dollar delimiters without escaping bugs or runtime crashes.
4. **Journey 4 (Teacher Batch Review & Keyboard Flow)**:
   - *As a college lecturer grading 50+ papers*, I want an Exam Queue Drawer and keyboard shortcuts (`[V]` to Quick-Verify, `[J]/[→]` for Next, `[K]/[←]` for Prev) to immediately sign off on grades and update `/api/results/{filename}/verify`.

---

## 3. Test Specification & Guarantees

| # | What is Guaranteed | Test Function | Type | Result | Evidence |
|---|--------------------|---------------|------|--------|----------|
| 1 | Complete HTML5 doctype, charset UTF-8, viewport, and title | `test_doctype_and_metadata` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 2 | Typography assets linked (Geist & JetBrains Mono) | `test_font_assets_linked` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 3 | KaTeX stylesheet and auto-render JS linked | `test_katex_math_assets` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 4 | Core DOM containers exist (`gradesContainer`, `blocksContainer`, `queueDrawer`, `bboxOverlay`, etc.) | `test_core_dom_containers_exist` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 5 | Real test samples present in interactive tray | `test_real_test_samples_in_tray` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 6 | Obsidian theme and Datalab semantic color tokens defined | `test_obsidian_and_datalab_tokens` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 7 | Bounding box overlay styles present with `pointer-events: none` | `test_bounding_box_overlay_styles` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 8 | Keyboard shortcut badge styling present | `test_key_badge_styling` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 9 | KaTeX delimiters configured (`$$`, `$`, `\\[`, `\\(`) with `throwOnError: false` | `test_katex_delimiters_configured` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 10 | Keyboard listeners registered for `V`, `J`, `K`, `ArrowRight`, `ArrowLeft` | `test_lecturer_keyboard_shortcuts_registered` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 11 | Teacher quick-verify action bar and sign-off badge present | `test_teacher_verification_action_bar` | Unit | PASS | `pytest tests/test_playground_ui.py` |
| 12 | Root route `GET /` serves complete HTML | `test_serve_playground_root` | Integration | PASS | `pytest tests/test_playground_ui.py` |
| 13 | Real sample image route `GET /samples/{name}` serves image binary | `test_serve_samples_static` | Integration | PASS | `pytest tests/test_playground_ui.py` |
| 14 | Results queue endpoint `GET /api/results` returns file list and queue | `test_get_results_and_queue` | Integration | PASS | `pytest tests/test_playground_ui.py` |
| 15 | Quick-verify endpoint `POST /api/results/{filename}/verify` signs off and updates disk | `test_quick_verify_flow` | Integration | PASS | `pytest tests/test_playground_ui.py` |

---

## 4. Test Suite Execution Summary

### GLM Edition (`glm-version`)
```bash
python -m pytest tests/
# Output:
# tests/test_layout.py ..........                 [ 19%]
# tests/test_pipeline.py .......................... [ 70%]
# tests/test_playground_ui.py ...............     [100%]
# ================= 51 passed, 1 warning in 25.79s ==================
```

### Chandra Edition (`chandra-version`)
```bash
python -m pytest tests/
# Output:
# tests/test_layout.py ..........                 [ 19%]
# tests/test_pipeline.py ........................... [ 71%]
# tests/test_playground_ui.py ...............     [100%]
# ================= 52 passed, 1 warning in 25.56s ==================
```

**Combined Total: 103 passed, 0 failed (100% green).**
