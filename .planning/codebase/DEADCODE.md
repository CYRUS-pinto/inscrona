# Dead Code, TODOs, and Drift

**Analysis Date:** 2026-09-17

## Dead / Unreachable Code

**`_colab_generate` stub (never callable):**
- `main.py:693-701` unconditionally raises `NotImplementedError("Use _colab_grade_endpoint...")`. Nothing imports it; the live fallback is `_colab_grade_endpoint` (`main.py:704-725`). Safe to delete; keep the comment pointing at the real path.

**`GradeRequest` model (unused):**
- Defined `main.py:160-165` (`rubric`, `structured_rubric`, `return_ocr`, `return_question_breakdown`) but both grade endpoints take individual `Form(...)` params (`main.py:324-330`, `516-520`). Either adopt it or delete it - it currently misleads readers into thinking JSON-body grading exists.

**`GradeResult.is_pass` / `letter_grade` (unused):**
- Properties at `main.py:145-158` are never referenced in `main.py`, `templates/index.html`, or `mobile/`. The web UI reimplements thresholds inline (`index.html:783-808`); mobile badge logic lives in `mobile/src/components/UI/Badge.tsx`. Wire them into CSV/list responses or delete.

**`GET /api/pair` (broken, effectively dead):**
- `main.py:474-494` declares `GET` with a `PairRequest` JSON body - unreachable from browsers, `curl` GET norms, and the mobile client, which calls `GET /api/pair` with no body (`mobile/src/api/client.ts:74-76`) → guaranteed 422. `DEPLOYMENT.md:118-131` documents it as working. Fix: change to `POST /api/pair` (body) or `GET /api/pair?base_url=...` (query), and update `getPairingInfo()` to match.

**Redundant imports:**
- `import httpx` at `main.py:20` plus a second `import httpx` inside `_colab_grade_endpoint` (`main.py:709`); `from functools import lru_cache` (`main.py:15`) never used; `asynccontextmanager` (`main.py:16`), `Set`/`Header`/`Field`-adjacent extras (`main.py:14,22`) partially unused. Harmless but noisy in the most-read file.

**One-off scripts (keep, but quarantine):**
- `run_ocr.py` (raw Ollama probe, hardcoded `test_resized.jpg` path), `resize.py` (hardcoded absolute Windows paths, `resize.py:3-4`), `test_task2.py` (manual Task-2 probe with mojibake docstring), `tunnel_test.py` (superseded by `tunnel.py`/`tunnel_bg.py`), `bench_5.ps1` (benchmark, absolute image dir default). None are referenced by `start.py`, `main.py`, or docs' quickstart. Move to `scripts/archive/` with a README note so root stays operator-clean.

**Orphan artifacts:**
- `database.db` (+ `-shm`/`-wal`) at repo root: zero references in code (no `sqlite3` import anywhere); `.gitignore:31-33` ignores the main file but not `-shm`/`-wal` consistently. Leftover from an abandoned DB experiment - delete or document.
- `Buzz_0.5.22_x64-setup_alpha-unsigned.exe` listed in `.gitignore:68` yet present on disk; `IMG_1226.jpg`/`IMG_1227.jpg`, `test_ocr.jpg`, `test_resized.jpg`, `test_data/` similarly gitignored-but-present. Working tree and index disagree - run `git status` and clean untracked large binaries.

## TODOs / FIXMEs (grep-verified)

- `main.py:595`: `result_dict["processing_time_ms"] = 0  # TODO: track actual time` - mobile grades report 0ms; fix by timing `mobile_grade` like `/grade` does (`main.py:333,394`).
- No `TODO/FIXME/HACK/XXX` markers elsewhere in `main.py`, `start.py`, `mobile/src/api/client.ts`, or `test_pipeline.py` - the debt is unmarked, which is worse (see RISKS.md).

## Drift: fields the UI reads but the API does not send (and vice versa)

**Web UI (current, healthy):**
- `templates/index.html:712-714` (`marksOf`/`confOf`) and `:789-792` already coalesce `total_marks ?? marks` / `overall_confidence ?? confidence` - the `e3c976d` fix landed in both server (`main.py:198-209`, `230-235`) and client. No action.

**Mobile types (stale, needs migration):**
- `mobile/src/types/index.ts:1-13` expects `{id, marks, confidence, rubric, image_url, created_at, status, progress_stage}`; the server sends `{job_id, total_marks, max_total_marks, percentage, overall_confidence, confidence_level, feedback, question_grades, ocr_text, processing_time_ms, model_used, fallback_used, flags, timestamp}`. Every mobile screen reading `result.marks`/`result.confidence`/`result.id`/`result.status` renders `undefined`.
- `BackendHealth` (`index.ts:22-29`) matches `/api/health` but `healthCheck()` calls `/health` (`client.ts:70-72`), whose `{"status":"ok"}` shape lacks `models`/`version` → runtime `undefined` on `health.models.ocr`.
- `UploadProgress.result?: GradeResult` (`index.ts:31-37`) inherits the same stale shape; `connectProgress` keys on `progress.result?.id` (`client.ts:148`) while the server emits `job_id`.

**Tests (stale assertions):**
- `test_pipeline.py:138-145` asserts `"marks" in result`, `isinstance(result["marks"], int)`, `0 <= marks <= 10` - the server now returns float `total_marks` (e.g. `20.0`, `PROGRESS.md:748`) plus `percentage`. `test_ocr_quality` (`test_pipeline.py:174-201`) and edge cases (`:203-228`) inherit the same shape assumption and use `timeout=300`, below the 600s server ceiling. Update assertions to `total_marks`/`overall_confidence` or re-add compatibility keys.

**Docs (stale contracts):**
- `DEPLOYMENT.md:101-115` endpoint table omits `response_model` shapes and the `/sentry-debug` route; `DEPLOYMENT.md:118-131` shows `GET /api/pair` with an `Authorization` header but no `base_url` body, which 422s; `DEPLOYMENT.md:66-80` Colab instructions say "set in local `.env`" though nothing loads `.env` (no dotenv dependency; `main.py:690` reads process env directly).

## Drift: WS token-gating vs open web UI

- The threat model is inverted: real-time progress (low sensitivity) requires a 24h bearer token (`main.py:609-610`, `80-87`), while grading arbitrary images on the owner's GPU and reading/exporting all PII (high sensitivity) is open (`main.py:323,191,215,249`). The web UI has no token concept at all (`templates/index.html` uses bare `fetch('/results')`, `:719`, and `xhr.open('POST','/grade')`, `:992`). Decide: either gate everything with one teacher token the web UI stores in `localStorage`, or explicitly document "single-user local tool, tunnel URL is the secret" and shorten tunnel lifetimes (`tunnel.py:34-36` keeps 60s; `tunnel_bg.py:35-38` keeps 3min - both fine, but `PROGRESS.md:756` primary path is long-lived localtunnel).

## Drift: mobile client vs current API shapes (full list)

| # | Mobile expectation | Server reality | File:line |
|---|--------------------|----------------|------------|
| 1 | `POST /grade` (unauthenticated) | Intended mobile route is `POST /api/grade` (gated), currently 500s | `client.ts:91` vs `main.py:515` |
| 2 | `GET /health` → `BackendHealth` | `/health` returns `{"status":"ok"}` only; `BackendHealth` lives at gated `/api/health` | `client.ts:70-72` vs `main.py:174-176,497` |
| 3 | `GET /api/pair` with no args → `PairingInfo` | Requires bearer token + `PairRequest{base_url}` body; 401/422 | `client.ts:74-76` vs `main.py:474-475` |
| 4 | WS `/ws/progress` with no token | Requires `?token=`; closes 4001 otherwise | `client.ts:139-143` vs `main.py:610,80-87` |
| 5 | `result.id`, `result.marks`, `result.status` | `job_id`, `total_marks`, no `status` field | `index.ts:1-13` vs `main.py:128-143` |
| 6 | `gradeImage` sends `Authorization` header to `/grade` | `/grade` ignores auth headers harmlessly; token is dead weight | `client.ts:91-97` vs `main.py:323-330` |
| 7 | `exportCsv` sends `Authorization` to `/results/export.csv` | Endpoint ignores it; any tunnel visitor can download | `client.ts:116-121` vs `main.py:215` |
| 8 | Offline queue retries 3×, polls every 30s | Each retry re-runs a ~4min GPU job; `processQueue` interval (`history.tsx:42`) compounds R1 | `uploadStore.ts:44-80`, `history.tsx:38-43` |

## Recommended deletion/rename pass (safe, no behaviour change)

1. Delete `_colab_generate` (`main.py:693-701`); keep `_colab_grade_endpoint`.
2. Delete `GradeRequest` or adopt it in both grade endpoints (`main.py:160-165`).
3. Deduplicate `import httpx`; drop `lru_cache`/`asynccontextmanager` if still unused after a lint pass (`main.py:15-16,20,709`).
4. Move `run_ocr.py`, `resize.py`, `test_task2.py`, `tunnel_test.py` to `scripts/archive/`; confirm `tunnel_bg.py` vs `tunnel.py` keepalive split is intentional or merge.
5. Remove or env-gate `/sentry-debug` (`main.py:179-183`).
6. Decide `database.db` fate (delete + document, or `.gitignore` the `-shm`/`-wal` pair too).

---

*Concerns audit: 2026-09-17*
