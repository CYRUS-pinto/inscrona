# Architecture

**Analysis Date:** 2026-09-17

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              Clients (no shared contract)                    │
├──────────────────┬──────────────────┬───────────────────────┤
│  Web playground  │   Mobile (Expo)  │   curl / tests        │
│ `templates/`     │   `mobile/`      │   `test_pipeline.py`  │
│ `index.html`     │   `src/api/`     │   `bench_5.ps1`       │
│  open, no auth   │   token-gated*   │   open, no auth       │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI (`main.py`, 790 lines)                  │
│  web routes │ mobile `/api/*` │ WS `/ws/progress`           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│   Inference: local Ollama → Colab fallback (`main.py:728`)   │
│   `glm-ocr` OCR → `llama3.2:3b` grade → `results/*.json`     │
└─────────────────────────────────────────────────────────────┘
```

\* Mobile *intends* token-gating but its calls miss the gated endpoints (see § Drift below and DEADCODE.md).

## Request Lifecycle Maps

### POST /grade (open web grading) — `main.py:323-462`

1. Parse multipart: `file: UploadFile`, `rubric/structured_rubric/return_ocr/return_question_breakdown` forms (`main.py:324-330`); `job_id = uuid4().hex[:12]` (`main.py:332`)
2. Read bytes, reject empty; extension allowlist `.jpg/.jpeg/.png/.heic/.heif/.webp` (`main.py:339-348`); persist to `uploads/{job_id}{ext}` (`main.py:347-349`)
3. `Image.open` + `verify()` + reopen; HEIC→JPEG convert (`main.py:352-362`); resize longest edge to `MAX_LONGEST_EDGE=2000` (`main.py:367-374`); base64 the file (`main.py:377-378`)
4. `await _grade_with_fallback(image_b64, rubric, job_id, ...)` (`main.py:382-387`) - sequential local Ollama OCR (~177-231s) then grading (~24-42s); Colab fallback if configured
5. Parse optional `structured_rubric` JSON **after** inference and merge into display string only - too late to affect grading (`main.py:397-407`)
6. Server-side `percentage = round(100*total/max, 1)` (`main.py:410-413`); assemble `result_data`, append quality flags (`main.py:414-439`); validate via `GradeResult` (`main.py:442-446`)
7. Write `results/{job_id}_grade.json` (`main.py:449-452`); fire-and-forget `_broadcast_progress(job_id, completed)` (`main.py:455-460`); return `final_result`

### GET /results — `main.py:191-212`

- Glob `results/*_grade.json` sorted by mtime desc; per file read+parse, map `total_marks→marks`, `overall_confidence→confidence` with legacy fallback (`main.py:198-209`); skip-on-error (`main.py:210-211`). **No pagination, no auth.**

### GET /results/export.csv — `main.py:215-246`

- `StreamingResponse` generator; header `job_id,marks,confidence,feedback` (`main.py:221`); rows sorted oldest-first (`main.py:226`); feedback written **verbatim, no CSV-formula sanitisation** (`main.py:230-235`). **No auth.**

### GET /results/{job_id} — `main.py:249-258`

- Read `results/{job_id}_grade.json`, inject `job_id` + `timestamp` (`main.py:256-257`); 404 if missing. **No auth; `job_id` is 12 hex chars, enumerable via /results.**

### GET /api/pair — `main.py:474-494` (BROKEN, see DEADCODE.md)

- Declared `GET` with `PairRequest` body (`base_url`) **plus** `verify_token` dependency; mints `secrets.token_urlsafe(16)`, 24h expiry, returns `{token, url, expires_at, qr_data}` (`main.py:477-494`). GET-with-body is unreachable from the mobile client (`mobile/src/api/client.ts:74-76` sends no body) → FastAPI 422 in practice.

### GET /api/health — `main.py:497-512` (token-gated)

- Requires `verify_token`; probes `OLLAMA_URL/api/tags` with sync `requests.get(timeout=5)` (`main.py:501`); reports per-model loaded flags. Mobile `healthCheck()` calls `/health` instead (`mobile/src/api/client.ts:70-72`) so it never exercises this.

### POST /api/grade — `main.py:515-606` (token-gated, BROKEN, see RISKS.md R4)

- Same upload→convert→resize→inference shape as `/grade` but with `_broadcast_progress` stages (`main.py:526-530`, `539-543`, `565-580`), then `result.setdefault("ocr_text","")` + `GradeResult(**result)` at `main.py:589-590` **without `job_id`** → Pydantic ValidationError → HTTP 500 on every call. `processing_time_ms` hardcoded `0` with TODO (`main.py:595`).

### WS /ws/progress — `main.py:609-635` (token-gated, query param)

- `ws_auth(websocket, token)` closes 4001 on bad/expired token (`main.py:80-87`); `accept()` (`main.py:617`); loop expects `{"action":"subscribe","job_id"}` (`main.py:622-630`); cleanup on disconnect (`main.py:631-635`). Progress pushed by sync `_broadcast_progress` via `asyncio.create_task(ws.send_json(...))` (`main.py:638-649`).
- Mobile `connectWebSocket()` (`mobile/src/api/client.ts:139-162`) opens `/ws/progress` **with no `?token=`**, so the server closes it immediately; its `onmessage` routes on `progress.result?.id` (`client.ts:148`) but the server sends `result.job_id` - double mismatch, progress never renders.

### GET /health, GET /, GET /sentry-debug — `main.py:174-188`

- `/health` sync def returns `{"status":"ok"}`; `/` serves `templates/index.html`; `/sentry-debug` deliberately raises `ZeroDivisionError` to test Sentry.

## Data Flow

```
phone/camera scan ─┐
web file input ────┼─► multipart POST /grade ─► uploads/{job_id}.jpg ─► PIL verify/HEIC-convert/resize(≤2000px)
                   │                                                        │
                   │                                                        ▼ base64
                   │                                              _grade_with_fallback()
                   │                                               ├─ _ollama_generate("glm-ocr", OCR_PROMPT, images)  ~3-4 min
                   │                                               ├─ _ollama_generate("llama3.2:3b", GRADING_PROMPT, format_json)
                   │                                               └─ on local failure → _colab_grade_endpoint() (httpx, 600s)
                   │                                                        │ JSON {total_marks, max_total_marks, ...}
                   │                                                        ▼
                   └◄── GradeResult JSON ◄── validate ◄── results/{job_id}_grade.json ──► /results, /results/{job_id},
                                                                                            export.csv, web history, mobile history
```

- OCR prompt: `main.py:265-277`; grading template: `main.py:279-317` (forces `model_used: llama3.2:3b`, `fallback_used: false` in the LLM output - the server overwrites both at `main.py:425-426`)
- Measured timings (`PROGRESS.md`): OCR 177-231s + grading 24-42s ≈ 140-255s per paper; 5-paper benchmark 710s total
- Storage convention: `uploads/{job_id}{ext}` image, `results/{job_id}_grade.json` grade; no DB, no object storage, no queue (`CONSTRAINTS.md`)

## Module Responsibilities

| Module | Owns | File |
|--------|------|------|
| FastAPI app + all routes + inference + storage | everything server-side (790 lines, no router split) | `main.py` |
| Pydantic contracts | `RubricCriteria`, `GradingRubric`, `QuestionGrade`, `GradeResult`, `GradeRequest` (unused), `PairRequest` | `main.py:93-165,470-471` |
| Pairing/auth + WS registry | `PAIRING_TOKENS`, `ACTIVE_WS`, `verify_token`, `ws_auth`, `_broadcast_progress` | `main.py:62-87,638-649` |
| Inference engine | `_ollama_generate`, `_colab_generate` (stub), `_colab_grade_endpoint`, `_grade_with_fallback` | `main.py:651-790` |
| Launcher + pre-flight | Ollama reachability, model presence, dir creation, uvicorn boot | `start.py` |
| Web playground | Upload form, XHR to `/grade`, history table, CSV link, OCR drawer, badges | `templates/index.html` |
| Mobile API layer | `ApiClient`: pairing store, grade/history/CSV calls, WS progress | `mobile/src/api/client.ts` |
| Mobile state | `authStore` (pairing), `uploadStore` (offline queue, max 3 retries, 100 cached results) | `mobile/src/store/` |
| Mobile screens | camera/gallery capture, review, processing (WS), result, history, settings | `mobile/app/` |
| Tunnel scripts | Pinggy expose (`tunnel.py` 60s keepalive, `tunnel_bg.py` 3min) | `tunnel.py`, `tunnel_bg.py` |
| Tests/bench | `test_pipeline.py` (stale-key assertions), `test_task2.py` (manual Ollama probe), `bench_5.ps1` | repo root |
| One-off utils | `run_ocr.py` (raw Ollama probe), `resize.py` (hardcoded local paths) | repo root |
| Colab fallback server | Remote `/grade` the local `_colab_grade_endpoint` POSTs to | `Inscrona_Colab_Remote_Inference.ipynb` |

## Layers

**Client layer** (`templates/index.html`, `mobile/`): capture/upload, render grades, history, CSV export. Depends on: HTTP API. Used by: teachers/phones. Note: web and mobile assume **different** response shapes (web handles both via `marksOf/confOf` at `index.html:712-714`; mobile assumes old `{id, marks, confidence, status}` at `mobile/src/types/index.ts:1-13`).

**API layer** (`main.py` routes): multipart parsing, validation, file persistence, result assembly. Depends on: inference layer + filesystem. No service/repository split; route handlers own business logic inline.

**Inference layer** (`main.py:651-790`): Ollama streaming + Colab fallback. Depends on: Ollama HTTP, `COLAB_INFERENCE_URL`. Used by: both `/grade` and `/api/grade`.

**Store layer** (`uploads/`, `results/`, `database.db` (orphan)): flat JSON files keyed by 12-char job id. No index, no locking, no migration.

## Entry Points

- `python start.py` → pre-flight → `uvicorn.run("main:app", 0.0.0.0:8000)` (`start.py:80-107`)
- `GET /` → web UI; `POST /grade` → grading; `GET /results*` → history/export; `/api/*` → mobile (gated); `/ws/progress?token=` → progress
- `npx localtunnel --port 8000` / `tunnel.py` → public URL; Colab notebook → fallback inference URL
- Mobile deep entry: `mobile/app/index.tsx` → `(tabs)/camera.tsx` → `review/[id]` → `processing/[id]` (WS) → `result/[id]`

## Architectural Constraints

- **Threading/event-loop:** single-process uvicorn; sync `requests.post(..., timeout=600)` blocks the loop per grading request (~4 min) - only one grading at a time in practice (RISKS.md R1)
- **Global state:** `PAIRING_TOKENS` + `ACTIVE_WS` are in-memory dicts (`main.py:62-63`) - lost on restart, no expiry sweeper (expired tokens only purged lazily on use at `main.py:74-76`), WS sets never pruned on job completion
- **Model sequencing:** `keep_alive: 0` unloads each model after use to fit consumer GPUs; callers rely on `ollama ps` emptiness as proof (`PROGRESS.md` Tasks 2,3,9)
- **Image ceiling:** `MAX_LONGEST_EDGE = 2000` (`main.py:48`); GLM-OCR silently drops larger images, hence the hard resize
- **Storage:** local FS only per `CONSTRAINTS.md`; `results/` + `uploads/` grow without bound (23 + 31 files at audit time)

## Error Handling

- HTTP-mapped failures: empty file / bad extension → 400 (`main.py:341-345`); image open failure → 400 (`main.py:363-365`); inference exhaustion → 500 (`main.py:389-391`); result validation → 500 (`main.py:442-446`)
- Silent-skip patterns: `/results` and CSV generators swallow per-file exceptions (`main.py:210-211`, `239-240`); `_broadcast_progress` swallows send errors (`main.py:646-647`)
- Sentry captures unhandled exceptions with PII (`main.py:32-39`); `/sentry-debug` (`main.py:179-183`) is an intentional 500

## Cross-Cutting Concerns

- **Logging:** `loguru` INFO per stage with `[job_id]` prefix (`main.py:336,349,452`); debug timing in `_ollama_generate` (`main.py:683`)
- **Validation:** Pydantic v2 with `field_validator` on rubric weights (`main.py:109-116`); `GradeResult` ranges + `confidence_level` regex (`main.py:128-143`); LLM arithmetic distrusted - percentage recomputed server-side (`main.py:413`)
- **Authentication:** Bearer-token pairing for `/api/*` + WS only; web routes intentionally open - the inversion (open grading, gated progress) is documented in RISKS.md R3

---

*Architecture analysis: 2026-09-17*
