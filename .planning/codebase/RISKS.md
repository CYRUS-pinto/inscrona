# Structural Risks

**Analysis Date:** 2026-09-17

Ranked by (blast radius × likelihood × cost to fix later). All references are `file:line`.

## R1 - Blocking `requests.post` inside async endpoints freezes the event loop (~4 min per grade) [CRITICAL]

- Evidence: `_ollama_generate` is a sync def using `requests.post(..., stream=True, timeout=600)` (`main.py:651-684`, call at `main.py:673`); invoked inline from async `_grade_with_fallback` (`main.py:744,748`) which is awaited from async `grade` (`main.py:382`) and `mobile_grade` (`main.py:583`). `GET /api/health` also blocks on `requests.get(timeout=5)` (`main.py:501`).
- Impact: one in-flight grading holds the loop for the full OCR+grade window (measured 140-255s/paper, `PROGRESS.md` Tasks 2/9/17). Concurrent `/grade` calls queue behind it; `/health` checks time out during grading; WS heartbeats stall. Throughput ceiling is effectively 1 grading at a time.
- Fix approach: move Ollama calls to `httpx.AsyncClient` streaming (dependency already present), or `asyncio.to_thread(_ollama_generate, ...)` as a minimal patch; add a `/health` fast-path that does not probe Ollama synchronously. Reproduce with two concurrent `POST /grade` and watch the second stall until the first completes.

## R2 - No auth on grading, history, or export; PII-bearing OCR world-readable [CRITICAL]

- Evidence: `POST /grade` (`main.py:323`), `GET /results` (`main.py:191`), `GET /results/export.csv` (`main.py:215`), `GET /results/{job_id}` (`main.py:249`), `GET /` (`main.py:186`) carry no dependency; only `/api/*` + WS require `verify_token`/`ws_auth` (`main.py:68-87`). OCR text contains student names/reg-nos (`PROGRESS.md` Task 1 output) and is served back via `/results/{job_id}` (`main.py:255`) and file reads.
- Impact: anyone with the tunnel URL (`tunnel.py`, localtunnel, `PROGRESS.md:756`) can grade arbitrary images on the owner's GPU, enumerate all 23+ results, and bulk-export PII as CSV. Pairing tokens gate the endpoints mobile does not even call (see R4), so the real attack surface is unauthenticated.
- Fix approach: put `verify_token` (or a teacher password / tunnel token) on `/grade`, `/results*`, `/results/export.csv`; or bind `start.py` to `127.0.0.1` by default and require an explicit `--public` flag for `0.0.0.0` (`start.py:107`). At minimum rate-limit `/grade` and strip `ocr_text` from list/CSV responses.

## R3 - Unbounded `uploads/` + `results/` growth, no pagination or retention [HIGH]

- Evidence: every grade persists an image (`main.py:347-348`, `535-536`) and a JSON result (`main.py:449-451`, `593-596`) forever; audit found 31 uploads / 23 results already. `/results` loads and parses every file per request (`main.py:195-211`); CSV re-reads all files per download (`main.py:226-240`); `.gitignore` only ignores contents, not growth (` .gitignore:36-41`).
- Impact: disk fills on a teacher laptop; `/results` latency degrades linearly; CSV export holds the response open while re-reading N files. No cleanup job, no max-age, no `DELETE` endpoint.
- Fix approach: cap `/results` (e.g. latest 50 + `?limit/offset`), add `DELETE /results/{job_id}` (removing both JSON and image), and a startup/periodic retention sweep (e.g. keep 30 days). Track counts in `/health`.

## R4 - `POST /api/grade` always 500s (missing `job_id`) and the mobile client never calls it [HIGH]

- Evidence: `mobile_grade` builds `GradeResult(**result)` at `main.py:589-590` but `_grade_with_fallback` returns no `job_id` (see `main.py:763-768`, `783-787`) while `GradeResult.job_id` is required (`main.py:130`) → ValidationError on every call; it then `return result` (raw dict, `main.py:606`) instead of the parsed model. Mobile `gradeImage()` POSTs to `/grade`, not `/api/grade` (`mobile/src/api/client.ts:91`), and `processing_time_ms` is hardcoded `0` with TODO (`main.py:595`).
- Impact: the entire token-gated mobile grading path is dead on arrival; all mobile traffic funnels into the unauthenticated `/grade` (compounding R2); WS progress for mobile jobs never fires correctly.
- Fix approach: construct the same `result_data` envelope as `/grade` (`main.py:414-428`, incl. `job_id`, server-side percentage, timing) in `mobile_grade`, return the validated model, and point `gradeImage()` at `/api/grade`; add one integration test that POSTs to `/api/grade` with a bearer token.

## R5 - WS progress is token-gated but unreachable: client omits token, server/client disagree on payload keys [HIGH]

- Evidence: server requires `?token=` (`main.py:610`) and `ws_auth` closes 4001 without it (`main.py:80-87`); client opens bare `/ws/progress` (`mobile/src/api/client.ts:139-143`). Client routes completions on `progress.result?.id` (`client.ts:148`) while server sends `result.job_id` + full `GradeResult` (`main.py:455-460`, `599-604`); client looks up listeners by upload id (`client.ts:124,148`) but nothing ever sends a subscribe frame with the server's `job_id` before grading starts. `_broadcast_progress` is sync fire-and-forget (`main.py:638-649`).
- Impact: `processing/[id].tsx` (`mobile/app/processing/[id].tsx:27`) subscribes to a socket the server rejects; no progress ever renders; reconnect loop (`client.ts:159-161`) retries forever against a 4001 close.
- Fix approach: append `?token=${token}` to the WS URL, send `{action:'subscribe', job_id}` immediately after the grade POST returns the server job id, and key listeners by that `job_id`; make `_broadcast_progress` async/awaited or drop it in favour of polling `GET /results/{job_id}`.

## R6 - CSV injection via unsanitised feedback text [MEDIUM]

- Evidence: `export_csv` writes `data.get("feedback","")` verbatim (`main.py:230-235`); feedback is LLM-generated free text (prompt at `main.py:279-317` imposes no character constraints) and the download is one click in the web UI (`templates/index.html:451`).
- Impact: a crafted answer sheet can produce feedback starting with `=`, `+`, `-`, `@` that executes as a formula when the teacher opens the CSV in Excel/Sheets (data exfiltration via `HYPERLINK`/`IMPORTXML` class).
- Fix approach: prefix-sanitise fields beginning with `=+-@` (prepend `'`) in `export_csv`, and emit a UTF-8 BOM so Excel parses quoting correctly. Same treatment for any future `marks` free-text columns.

## R7 - HEIC/resize path: format/extension mismatch, PNG never converted, error swallow [MEDIUM]

- Evidence: `/grade` converts only `.heic/.heif` (`main.py:357`), leaving `.png`/`.webp` to be re-saved as JPEG bytes under the original extension (`main.py:370-374`); `/api/grade` saves resized JPEG bytes to `saved_path` which may end `.png` (`main.py:558-563`). `img.verify()` + reopen (`main.py:354-355`) still leaves truncated/corrupt images to fail later at base64/inference time; per-file read errors in history/CSV are silently skipped (`main.py:210-211`, `239-240`).
- Impact: downstream viewers sniff MIME mismatches; corrupt uploads burn a 4-minute inference slot before failing; silent skips hide data loss (a teacher sees fewer rows with no error).
- Fix approach: normalise every upload to `.jpg` after open (not just HEIC), `img.load()`/`verify` once with explicit 400 on failure, log skipped files in `/results` with a `warnings` count instead of swallowing.

## R8 - Timeout and retry handling: 600s ceilings, no client guidance, test timeouts shorter than reality [MEDIUM]

- Evidence: Ollama calls use `timeout=600` (`main.py:657,673`, `714,718-724`); `test_pipeline.py` uses `timeout=300` per grade (`test_pipeline.py:134,189,216,223`) while measured grades run up to ~255s and benchmarks average 142s; web XHR in `templates/index.html:992` sets no timeout UI beyond the spinner; mobile `uploadStore` retries 3× (`mobile/src/store/uploadStore.ts:18,46-78`) with no backoff against a 4-minute endpoint.
- Impact: slow papers flake in tests but pass manually; mobile retries triple-submit the same 4-minute job, multiplying GPU load.
- Fix approach: single timeout constant shared by server/tests/client; exponential backoff + idempotency key (`job_id` returned synchronously, result polled) instead of blind POST retries.

## R9 - Secrets and telemetry hygiene: hardcoded Sentry DSN + PII, intentional 500 endpoint [MEDIUM]

- Evidence: `SENTRY_DSN` hardcoded with `send_default_pii=True`, `traces_sample_rate=0.1` (`main.py:32-39`); `/sentry-debug` raises unconditionally (`main.py:179-183`); `DEPLOYMENT.md:86-97` documents `.env` keys the code never reads (no dotenv loader, `OLLAMA_URL`/`COLAB_INFERENCE_URL` are constants at `main.py:45,690`).
- Impact: DSN committed to git (`git log 8f5652a/e3c976d/f16c627`); request bodies (student PII) leave the laptop to Sentry EU ingest; anyone can trigger error-event spam via `/sentry-debug`.
- Fix approach: move DSN to env, default off in development; set `send_default_pii=False`; gate `/sentry-debug` behind env flag or delete it; either load `.env` or fix the docs.

## R10 - In-memory pairing/WS registries: no persistence, no expiry sweep, leak on restart [LOW]

- Evidence: `PAIRING_TOKENS`/`ACTIVE_WS` module dicts (`main.py:62-63`); expiry only checked lazily (`main.py:74-76`, `84-86`); WS sockets removed only on disconnect (`main.py:631-634`), never on job completion; restart invalidates all mobile pairings with no re-pair UX signal.
- Impact: stale sockets accumulate within a process; every server restart silently unpairs all phones (teachers re-scan QR with no error message explaining why).
- Fix approach: persist pairing tokens to disk (or document restart-unpairs prominently), sweep expired tokens + empty WS sets on an interval, and return a distinct `401 token_revoked_restart` the app can surface as "re-scan QR".

---

*Concerns audit: 2026-09-17*
