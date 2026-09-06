# Inscora — Dual-Engine Enterprise Exam Correction

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/CYRUS-pinto/inscrona/blob/main/Inscora_Colab.ipynb)

> **⚡ 1-Click Cloud Deployment (Free T4 GPU):** Click the badge above to launch the full Vision OCR + LLaMA 3.2 grading suite on Google's cloud with zero local battery or hardware usage.

Two independent, production-grade editions of the university exam-correction
pipeline. Run locally or in Google Cloud.

| Edition | OCR engine | Port | Folder |
|---|---|---|---|
| **Chandra edition** | Chandra OCR (Datalab) — local Ollama **or** Datalab hosted API | 8000 | [`chandra-version/`](chandra-version/) |
| **GLM edition** | GLM-OCR 0.9B — local Ollama, built-in **two-pass** high-accuracy retry | 8001 | [`glm-version/`](glm-version/) |

Each edition is fully self-contained (own venv, config, tests, docs) and runs
the identical pipeline:

```
phone photo → HEIC→JPEG → resize ≤2000px → blur check
           → OCR engine (keep_alive=0, unloaded after)
           → grading LLM llama3.2:3b (JSON-constrained, unloaded after)
           → results/{id}_grade.json + mobile-friendly results UI
```

## Why two editions

Your research flagged Chandra OCR-2 as the strongest on Indian handwriting and
an industry contact recommended GLM-OCR (94.6 OmniDocBench, tiny 0.9B footprint,
strong tables/LaTeX). Both are wired to their maximum working capacity:

- **Chandra edition**: local Ollama mode *and* Datalab cloud-API mode (fallback
  for GPU-less machines), page-level confidence + heuristic scoring.
- **GLM edition**: two-pass OCR (weak pages re-run with a high-accuracy prompt,
  better reading kept), temperature-0 transcription.

## Quick start (each edition)

```bash
cd chandra-version   # or glm-version
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
copy .env.example .env
# ollama pull llama3.2:3b  (+ the edition's OCR model — see its README)
run.bat              # Windows   |   ./run.sh   # Linux
```

Then open `http://localhost:8000` (Chandra) or `:8001` (GLM) — from any phone
too. See each edition's README for model tags, tunneling (Pinggy) and API docs.

## Tests (no GPU needed — model calls are mocked)

```bash
cd chandra-version && python -m pytest tests/ -v
cd glm-version     && python -m pytest tests/ -v
```

## Real test data

Your 60+ HEIC answer sheets (`Answer papers-…/IMG_1225.HEIC`…) work directly —
HEIC is converted automatically. Suggested validation: upload 10 sheets through
both editions with the same rubric, then diff `results/*.json` (marks, flags,
confidence) to choose the default engine per subject.
