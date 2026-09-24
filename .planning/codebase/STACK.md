# Technology Stack

**Analysis Date:** 2026-09-17

## Languages

**Primary:**
- Python 3.10+ - backend (`main.py`, `start.py`, `tunnel.py`, `tunnel_bg.py`, `test_pipeline.py`, `run_ocr.py`, `resize.py`, `test_task2.py`)
- TypeScript / TSX - mobile app (`mobile/src/`, `mobile/app/`), Expo Router screens
- HTML/CSS/JS (vanilla, no bundler) - web playground (`templates/index.html`, ~57KB)

**Secondary:**
- PowerShell - benchmark harness (`bench_5.ps1`)
- Jupyter Notebook - Colab remote-inference fallback (`Inscrona_Colab_Remote_Inference.ipynb`)

## Runtime

**Environment:**
- CPython 3.10+ with `uvicorn` serving `main:app` (`start.py:106-107`)
- Ollama at `http://127.0.0.1:11434` serving `glm-ocr` (OCR) + `llama3.2:3b` (grading), constants at `main.py:45`, `start.py:9-10`
- Node/Expo SDK 51 for mobile (`mobile/package.json:23`)

**Package Manager:**
- pip + `requirements.txt` (8 pins, all `>=` floor-only, no lockfile)
- npm/EAS for mobile (`mobile/package.json`, `mobile/eas.json`); `mobile/node_modules/` gitignored

## Frameworks

**Core:**
- FastAPI 0.110+ - entire backend (`main.py:171`); Pydantic v2 models (`main.py:93-165`); `loguru` logging; `sentry-sdk` 1.60+
- Expo Router 3.5 + React Native 0.76 + React 18.2 - mobile app (`mobile/package.json:22-41`)
- Zustand 4.5 (+ persist) - mobile state (`mobile/src/store/authStore.ts`, `mobile/src/store/uploadStore.ts`); TanStack Query 5.51 present but barely used

**Testing:**
- `pytest` + `fastapi.testclient.TestClient` - `test_pipeline.py:17,26` (imports pytest but uses ad-hoc `asyncio.run(run_all_tests())`, not pytest test functions)
- No JS test runner configured in mobile (no jest/vitest config; `lint` + `typecheck` scripts only, `mobile/package.json:13-14`)

**Build/Dev:**
- `uvicorn` (pulled transitively; not pinned in `requirements.txt`)
- `start.py` launcher with pre-flight checks (`start.py:60-73`) + `--check-only` flag
- EAS Build profiles (`mobile/eas.json`) for preview/production

## Key Dependencies

**Critical:**
- `requests>=2.31` - Ollama calls in `main.py:651-684`, `start.py:17-48`, `test_task2.py`, `run_ocr.py`. **This is the load-bearing risk**: sync `requests.post(..., timeout=600)` inside async endpoints (see RISKS.md R1)
- `httpx>=0.27.0` - Colab fallback path only (`main.py:709-725`); top-level `import httpx` (`main.py:20`) is redundant with the function-local import at `main.py:709`
- `pillow>=12.0` + `pillow-heif>=1.6.0` - HEIC open + resize (`main.py:53-56`, `main.py:352-374`)
- `sentry-sdk>=1.60.0` - hardcoded DSN at `main.py:32-39` with `send_default_pii=True`
- `pinggy` (Python SDK, **not in requirements.txt**) - `tunnel.py:1`, `tunnel_bg.py:4`; import-time hard dependency for tunnel scripts

**Infrastructure:**
- Ollama models: `glm-ocr:latest` (~2.2GB) + `llama3.2:3b` (~2.0GB); sequential load/unload via `keep_alive: 0` (`main.py:744,748`)
- Local filesystem store: `./uploads/`, `./results/` (`main.py:46-51`); `database.db` exists at repo root but **no code touches sqlite** (leftover/drift, see DEADCODE.md)
- Tunnels: Pinggy SDK (`tunnel.py`), localtunnel via npx, ngrok (Colab notebook), Tailscale (notes only) - see DEPLOYMENT.md remote-access section

## Configuration

**Environment:**
- `COLAB_INFERENCE_URL` (optional, `main.py:690`) - enables Colab fallback; empty string disables
- `ENVIRONMENT` (optional, `main.py:38`) - Sentry environment tag, defaults `development`
- `SENTRY_DSN` is **hardcoded** (`main.py:32`), not env-driven, despite `DEPLOYMENT.md:86-97` documenting a `.env` layout the code never loads (no `python-dotenv` dependency; `OLLAMA_URL` is a module constant, `main.py:45`)
- `.env*` files are gitignored (`.gitignore:56-58`) but nothing reads them - doc/code drift

**Build:**
- No `pyproject.toml`, no `tsconfig` strictness audit done; mobile `app.config.ts` + `eas.json` own the native build
- `templates/index.html` is served verbatim via `FileResponse` (`main.py:186-188`) - no build step, no CSP headers

## Platform Requirements

**Development:**
- Python 3.10+, Ollama running, `ollama pull glm-ocr llama3.2:3b`, `pip install -r requirements.txt`, `python start.py` (per `DEPLOYMENT.md:3-23`)
- Mobile: `cd mobile && npm install` / `npx expo install`; EAS login for device builds (`PROGRESS.md:762`)

**Production:**
- No production target exists: single-process uvicorn on `0.0.0.0:8000` (`start.py:107`), no workers, no reverse proxy, no auth on web routes, no retention/cleanup jobs. College-server deployment is aspirational (`start.py` docstring + `DEPLOYMENT.md:218-225` next steps)

---

*Stack analysis: 2026-09-17*
