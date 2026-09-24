# Phase 1: Colab Burst + Speed — Research

**Researched:** 2026-09-24
**Domain:** Local Ollama inference tuning + Colab free-GPU burst routing + perceived-speed UX (FastAPI, Windows laptop, no new deps)
**Confidence:** MEDIUM (code paths verified in-repo; GPU state and timings need Wave 0 measurement)

## User Constraints (from CONTEXT.md — locked)

1. Speed is top priority: p50 < 90s local, < 45s on Colab burst.
2. Colab free-GPU burst approved as the speed path (hybrid router: local-first offline default, Colab burst/opt-in). Interactive-attended use only — never 24/7 headless serving (ToS).
3. No new frameworks, services, models, or dependencies (CONSTRAINTS.md). `google-colab-cli` may be prepared in WSL but Windows can't run it.
4. "The user should never suffer": staged progress, elapsed ticker, honest timing copy, no spinner-forever, retry paths that preserve work.
5. Verification-before-completion: every task ends with runnable `<verify>` + real output. Mock-first tests (no GPU) for logic; timed runs for numbers.

Already shipped (do not replan): `_normalize_colab_result` adapter + 19 mocked tests (green); stdlib `.env` loader + non-fatal `check_colab()` (`MODE: local-only|hybrid`); dead `_colab_generate` stub deleted.

## Summary

Local grading is dominated by `glm-ocr` OCR at 177–231s/page [VERIFIED: PROGRESS.md Tasks 2/9] plus `llama3.2:3b` grading at 24–42s — ~140–255s/page total. The single biggest unknown is whether this Windows laptop has a usable NVIDIA GPU at all: `nvidia-smi` is absent (likely CPU-only), which would make the local < 90s target unreachable by tuning and promote Colab burst to the primary speed path. The code already contains the full fallback chain (`_grade_with_fallback` → `_colab_grade_endpoint` → `_normalize_colab_result`), but routing is failure-triggered only (no `?burst=true` opt-in, no health gate, no circuit breaker), the blocking `requests.post` inside `async def` freezes the event loop for the whole ~4 min window, and the Colab notebook's `/grade` still returns the legacy `{marks, confidence, feedback, ocr_text}` schema (covered server-side by the adapter, confirmed below).

**Primary recommendation:** Wave 0 proves CPU-vs-GPU in 10 minutes; if CPU-bound, build in this order — (1) async retrofit (throughput/honesty win, no latency change), (2) `?burst=true` + health-gated Colab routing with circuit breaker, (3) measured OCR tuning sweep, (4) burst-warm batch mode, (5) perceived-speed UX polish on top of the timed-stage UI that already exists.

## 1. GPU Presence Check (Windows laptop) + CPU-Bound Speedup Ladder

### 1a. Proof procedure (run in order, ~10 min)

| # | Command (PowerShell) | What it proves |
|---|----------------------|----------------|
| 1 | `Get-Command nvidia-smi; nvidia-smi -L 2>&1` | Absent = no NVIDIA driver visible to user PATH. CONTEXT already records NOT installed [VERIFIED: CONTEXT.md:28-29]. Also try `"$env:ProgramFiles\NVIDIA Corporation\NVSMI\nvidia-smi.exe" -L` — driver may exist without PATH. [ASSUMED — standard NVIDIA install path] |
| 2 | `ollama ps` (during a live grade) | `PROCESSOR` column reads `100% CPU` vs `100% GPU` — authoritative per-request proof of where that model executed [CITED: https://github.com/ollama/ollama/issues/9704 — `ollama ps` PROCESSOR column] |
| 3 | Server log: `%LOCALAPPDATA%\Ollama\server.log` — search `inference compute` | Line `inference compute id=... library=cuda|cpu` names the selected backend per model load [CITED: https://github.com/ollama/ollama/issues/9704 — `inference compute … library=cuda` log line] |
| 4 | `ollama show glm-ocr` + `ollama list` | Confirms model blobs present and parameter size (~0.9–1.1B vision + 3B grader) [VERIFIED: notebook pins `glm-ocr` + `llama3.2:3b`; STACK.md:53 sizes ~2.2GB/~2.0GB] |
| 5 | Timed probe: `Measure-Command { ollama run glm-ocr "test" }` or one `/grade` with `processing_time_ms` | CPU OCR ≈ 177–231s matches known CPU timings [VERIFIED: PROGRESS.md]; GPU T4 should cut vision tokens ~5–10× [ASSUMED — needs Wave 0 measurement] |

Decision rule: if step 2 shows `100% CPU` **and** step 3 shows `library=cpu` **and** step 1 finds no driver → laptop is CPU-only; local floor is unfixable and Colab becomes the speed path (record in PROGRESS.md, do not burn waves on local-only tuning beyond the cheap wins). If a GPU exists but Ollama picks CPU, suspect driver ≥ 551.61 requirement [CITED: https://docs.ollama.com/windows] or the `ggml-cuda.dll` discovery crash seen on RTX 4060 Laptop [CITED: https://github.com/ollama/ollama/issues/17375]; remedies (reinstall driver, `OLLAMA_LLM_LIBRARY` override) are operator steps, not code.

### 1b. Per-setting speedup ladder (if CPU-bound)

All knobs below are request-level `options` dict entries on the existing `/api/generate` call — no new dependency, CONSTRAINTS-safe. Current code sends only `{"num_predict": 2048, "temperature": 0.1}` [VERIFIED: main.py:691] and default `num_ctx` (Ollama default 4096) [CITED: https://docs.ollama.com/faq].

Predicted impact order (highest-first; magnitudes are [ASSUMED] until the Wave 0 sweep measures them):

1. **Image longest-edge 2000 → 1280–1600px for OCR.** Vision encode cost scales with pixel/token count; the 2000px ceiling exists because GLM-OCR silently drops >~2300px images [VERIFIED: main.py:74, TASKS.md:22]. Dropping to 1600 cuts pixels ~36%, to 1280 ~59%. Risk: small-handwriting legibility loss — gate on Phase 3 eval (transcript non-empty, marks ±2). Predicted: **largest single win, 20–40% OCR time cut.**
2. **JPEG quality 90 → 70–80 + strip to grayscale-safe RGB.** Smaller base64 payload and faster decode; text legibility survives 70–75 for handwriting scans in practice [ASSUMED]. Current code saves `quality=90, optimize=True` [VERIFIED: main.py:385,399]. Predicted: 5–15%.
3. **OCR prompt shortening.** Current `OCR_PROMPT` is ~200 words/8 guidelines [VERIFIED: main.py:291-303]. Every output token costs CPU decode; instructions 2,7,8 (crossed-out marking, spelling preservation, student details) inflate output. A terse variant ("Transcribe all visible text, preserve question numbers and layout.") cuts output tokens. Predicted: 10–20% on OCR decode.
4. **`num_predict` cap 2048 → 1024–1408 for OCR.** OCR output for one page (~1300 chars measured [VERIFIED: PROGRESS.md:75]) fits in ~500 tokens; 2048 only matters as a runaway ceiling. Capping stops repetition-loop tails (a known vision-model failure mode fixed by `repeat_penalty`/`repeat_last_n` in community Modelfiles [CITED: https://medium.com/@mhjorleifsson/local-accurate-and-fast-ocr-with-ollama-a530302eca39]). Predicted: 0–15% (tail insurance, not median).
5. **`num_ctx` — do NOT lower; consider raising to 8192 for glm-ocr.** Vision tokens consume context; `glm-ocr` crashes with `GGML_ASSERT` at default 4096 on table-heavy images and needs ≥8192 [CITED: https://github.com/ollama/ollama/issues/16696]. A community glm-ocr Modelfile likewise sets `num_ctx 8192` [CITED: https://medium.com/@mhjorleifsson/local-accurate-and-fast-ocr-with-ollama-a530302eca39]. Larger ctx costs RAM/VRAM but prevents 500s + runner restarts (~10s penalty each). Predicted: no speedup; **correctness/stability fix** that must precede any tuning sweep.
6. **Grading `num_predict` 2048 → 1024.** Grading output is one JSON object (~300–600 tokens); 2048 is 3–4× headroom. Predicted: 5–10% off the 24–42s grading stage.

Sweep protocol (Wave 1 task): fix `num_ctx=8192` for glm-ocr, then vary longest-edge {2000, 1600, 1280} × JPEG {90, 75} × OCR prompt {full, terse} on 3 fixed pages, recording `processing_time_ms` + transcript length + eval marks delta. 18 timed runs ≈ 18 × ~3 min CPU — schedule as an unattended batch, not interactive.

## 2. Colab Free-Tier Burst Design

### 2a. Notebook server contract (what `/grade` MUST return)

The server-side adapter already exists and is tested (19 mocked tests green [VERIFIED: CONTEXT.md:19-20]). Reading it directly [VERIFIED: main.py:719-759]:

- **New-schema passthrough:** if the dict contains `total_marks` or `overall_confidence`, the adapter fills defaults (`max_total_marks=10`, `confidence_level="medium"`, `question_grades=[]`, `flags=[]`, `model_used="colab_fallback"`, `fallback_used=True`, `ocr_text=""`) and returns it. So the notebook **should** return GradeResult-shaped keys: `total_marks, max_total_marks, overall_confidence, confidence_level, feedback, question_grades, ocr_text` (percentage is recomputed server-side in `grade()` [VERIFIED: main.py:436-439] — notebook MUST NOT be trusted for arithmetic).
- **Legacy fallback:** the current notebook returns `{marks, confidence, feedback, ocr_text}` [VERIFIED: Inscrona_Colab_Remote_Inference.ipynb:227-232]; the adapter maps `marks→total_marks`, buckets confidence to high/medium/low (≥0.75 / <0.4) [VERIFIED: main.py:746-759], appends flag `colab_legacy_schema`. Works today, no notebook edit strictly required — but upgrading the notebook to new-schema output removes the `colab_legacy_schema` flag noise and the `marks`-as-dict/string coercion path.
- **Notebook bugs to fix when touched:** `import io` sits AFTER the `/grade` handler that uses `io.BytesIO` (cell executes top-to-bottom so it works at runtime, but a re-ordered run breaks) [VERIFIED: ipynb:179 vs 238]; HEIC branch never re-encodes non-HEIC PNG/WebP to JPEG before base64 (mirrors local R7); bare `except:` in `/health` swallows diagnostics [VERIFIED: ipynb:170-171].

### 2b. Tunnel options from a Colab runtime

| Option | Status | Notes |
|--------|--------|-------|
| **pyngrok** (current notebook) | Works, keep | `ngrok.connect(8000, bind_tls=True)` [VERIFIED: ipynb:108]; free tier: 1 session, ~40 conn/min — fine for 1-teacher burst. Needs auth token pasted per session. |
| **Colab `google.colab` port-forward / local runtime** | Not viable for this direction | Colab→laptop requires the laptop to dial out; the laptop is behind NAT. Reject. [ASSUMED — standard NAT constraint] |
| **Cloudflare quick tunnel (`cloudflared`)** | Alternative, no account | Runs in Colab (`!cloudflared tunnel --url :8000`), URL rotates per session same as ngrok. No new server-side dep (URL is just a string in `.env`). Allowed under CONSTRAINTS (not a production service, just a transport). [ASSUMED — well-known tool, needs Wave 0 smoke test] |
| **Tailscale in Colab** | Rejected for Phase 1 | Needs auth key + userspace networking in the Colab VM; fragile on free tier. Park for Phase 4 packaging. |

**Rotation handling (required regardless of tunnel):** the public URL changes every Colab session. Design: `COLAB_INFERENCE_URL` stays a plain env string [VERIFIED: main.py:716]; add a `POST /api/colab-url` (token-gated) or reuse startup `check_colab()` probe [VERIFIED: start.py:83-100] plus a per-request health gate ( §2c) so a stale URL degrades to local-only with a log line instead of a 500. Operator copies one URL from notebook output → pastes into `.env` or the new endpoint → `MODE: hybrid` confirms. Never auto-scrape ngrok APIs (new dep, flaky).

### 2c. Health-check + circuit-breaker pattern for `COLAB_INFERENCE_URL`

Current state: `check_colab()` probes `GET {url}/health` once at startup, advisory-only [VERIFIED: start.py:83-100]; `_grade_with_fallback` tries local first and only touches Colab on local exception, with `timeout=600` and no breaker [VERIFIED: main.py:786-845]. Gaps: no `?burst=true` opt-in (burst is unreachable when local succeeds slowly — the common case), no consecutive-failure counting, a dead tunnel adds its full 600s timeout to every grade.

Recommended pattern (stdlib + httpx only, no new dep):

- `GET {url}/health` (notebook already serves `{status, models, backend: "colab"}` [VERIFIED: ipynb:156-171]) with **short timeout (5–8s)** before routing burst traffic.
- Circuit state in module globals: `CLOSED → OPEN` after N=3 consecutive Colab failures (any of timeout/5xx/parse), half-open probe after cooldown 60s; while OPEN, skip Colab instantly (fail-fast to local) and surface `colab_circuit_open` in `/health` + `flags`.
- `?burst=true` on `POST /grade` means: health-gate Colab first; if healthy → Colab primary (skip slow local OCR); if unhealthy/circuit-open → local with `fallback_used=False` and flag `burst_unavailable`. Default (no param) keeps today's local-first behavior (offline-safe default preserved).
- Timeout split: health probe 8s; `/grade` POST stays 600s (Colab T4 still needs minutes for OCR+grade on first pull).

### 2d. 90-min idle / 12h limits handling

Free-tier envelope [CITED: https://research.google.com/colaboratory/intl/en-GB/faq.html — max ~12h, dynamic limits, no guarantees; idle ~90 min widely reported, treat as observed-not-promised]:

- **Design for sessions, not servers:** each Colab boot re-pulls models (~5 min first run [VERIFIED: ipynb:81-85]) and mints a fresh tunnel URL (§2b). The local backend MUST treat Colab as ephemeral: every burst grade re-validates via health gate; expiry mid-batch falls back to local per-paper (batch continues degraded, never aborts).
- **Idle:** grading traffic itself counts as execution, but browser-tab interaction is what resets Colab's idle clock — the teacher keeps the Colab tab open during a burst class period (attended use, §2e). Add a notebook-side `GET /health` the teacher can watch; on disconnect the local circuit opens and the UI shows "burst ended, continuing locally."
- **12h hard cap:** no mitigation; document "start a fresh Colab session per school day" in operator README (Phase 4). Never add auto-reconnect bots (ToS, §2e).

### 2e. ToS-safe attended-use framing

Colab's FAQ prioritizes interactive notebook use and restricts bypassing the notebook UI for headless serving [CITED: https://research.google.com/colaboratory/intl/en-GB/faq.html]. Safe framing (already locked in CONTEXT): teacher opens the notebook, clicks Run, keeps the tab open during grading — a human driving an interactive session, burst-scoped (one class period), never 24/7, never multi-user serving. Copy for README/UX: "Start burst when you sit down to grade; stop it when you leave." No keep-alive pings, no headless auto-restart, no sharing one tunnel across teachers.

## 3. Async Retrofit (exact call sites, risks, why throughput)

**Call sites** [VERIFIED: main.py]: `_ollama_generate` is `def` (sync) using `requests.post(..., stream=True, timeout=600)` [VERIFIED: main.py:677-699]; it is called **without await** from `async def _grade_with_fallback` at lines 802 and 806 [VERIFIED]; which is awaited from `async def grade` (line ~408) and `mobile_grade`. `GET /api/health` also blocks on sync `requests.get(timeout=5)` [VERIFIED: main.py:501 per RISKS.md R1]. `httpx>=0.27.0` is already a dependency [VERIFIED: requirements.txt:8] and `_colab_grade_endpoint` already uses `httpx.AsyncClient` correctly [VERIFIED: main.py:772-783] — so the fix is CONSTRAINTS-clean.

**Two options (recommend A, keep B as fallback):**

- **A. `asyncio.to_thread(_ollama_generate, …)` at the two call sites.** ~4-line diff, keeps streaming/parse logic untouched, zero behavior change to Ollama wire format. Requires `await` on the call: `ocr_text = await asyncio.to_thread(_ollama_generate, "glm-ocr", OCR_PROMPT, …)`. `asyncio` is already imported [VERIFIED: main.py:11]. Risk: threadpool thread held 4 min per grade (fine at teacher scale; document max-workers note).
- **B. Rewrite `_ollama_generate` on `httpx.AsyncClient` streaming** (`client.stream` + `aiter_lines`, per httpx async docs [CITED: https://www.python-httpx.org/async]). Larger diff, must re-verify chunk parsing + `done` break + timeouts. Benefit: no thread held; connection pooling (minor here — one Ollama host). Risk: subtle streaming regressions under the 600s window.

**Why throughput, not single-grade latency:** neither option makes one OCR run faster — the model still takes 177–231s. The win is the event loop stays free: concurrent `POST /grade` #2 no longer queues behind #1's 4-minute block; `/health` and `GET /results` answer during grading; WS heartbeats don't stall (RISKS.md R1 impact statement). Measure with two concurrent grades: before = serialized (~8 min wall), after = overlapped (~4 min wall on Colab/GPU, still serialized on local CPU Ollama queue — report honestly). Single-grade p50 moves only via §1b tuning and §2 burst.

**Risks:** (1) `_broadcast_progress` is sync fire-and-forget via `asyncio.create_task` [VERIFIED: main.py:664-675] — safe under threads but still un-awaited; leave as-is in this phase. (2) `GradeResult` validation + percentage recompute unchanged — no contract drift. (3) TestClient-based tests are sync — `to_thread` works under TestClient; verify with existing suite + the 19 adapter tests.

## 4. Burst-Warm Mode Design (N-paper batch, sequential-VRAM golden rule)

Golden rule (locked): models load/unload sequentially via `keep_alive=0`; `ollama ps` empty after each stage [VERIFIED: PROGRESS.md:75-79, main.py:802/806 pass `keep_alive=0`]. Both local AND notebook paths already use `keep_alive=0` [VERIFIED: ipynb:132-138,196,206]. Rationale: consumer GPUs (T4 15GB usable, laptop iGPU/CPU) cannot hold glm-ocr + llama3.2:3b resident together — overlap risks OOM.

**Burst-warm = keep the *session* warm, not the *models* resident:**

- `POST /grade?burst=true&warm=1` (or a `POST /api/burst-warm` prime call): on first paper, the router health-gates Colab (§2c); on success it pre-pulls by hitting notebook `/health` (models already pulled in cell 2) — i.e., "warm" means *tunnel verified + models confirmed present*, NOT `keep_alive>0`.
- Per paper in the batch: OCR (`keep_alive=0`) → grade (`keep_alive=0`) sequentially, exactly as today. No concurrency against one Ollama daemon (local or Colab) — N papers run back-to-back, each ~45s on T4.
- Batch UX: web UI loops its existing single-file `runGrade()` N times (no server queue table — CONSTRAINTS forbids Redis/BullMQ; local-FS only). Server stays stateless per paper; `results/{job_id}_grade.json` per paper is the batch record [VERIFIED: main.py:449-452 pattern].
- **End-of-batch discipline:** after the last paper (or on any batch abort), issue `POST /api/generate {"model": "glm-ocr", "keep_alive": 0}` + same for `llama3.2:3b` (the documented unload pattern [VERIFIED: PROGRESS.md:76-79]) against the Colab daemon, then log `ollama ps`-equivalent (`GET /api/ps` if exposed, else notebook `/health` showing `loaded:false`). Zero resident models is the acceptance check, recorded in PROGRESS.md.
- `?burst=true` without `warm`: identical routing, minus the pre-flight prime (single-paper path).

What NOT to build: server-side job queue, background workers, persistent keep-alive, parallel Ollama calls — all violate CONSTRAINTS or the VRAM rule.

## 5. Perceived-Speed UX (broadcast vs. displayable)

**What the backend already broadcasts** [VERIFIED: main.py:801-804,836 + _broadcast_progress 664-675]: stage frames `{stage:"ocr",progress:20}`, `{stage:"grading",progress:50}`, `{stage:"ocr",progress:10,message:"Local failed, trying Colab…"}` — but ONLY to WS subscribers in `ACTIVE_WS[job_id]`, and **WS is pairing-token-gated** (`?token=` + `ws_auth` 4001-close [VERIFIED: main.py:106-113]) while **web `/grade` is open (no token)**. So the web UI can never receive these frames today — verified architectural mismatch (RISKS.md R5; ARCHITECTURE.md WS section).

**What the web UI honestly shows today** [VERIFIED: templates/index.html:938-1033]: timed stages (Upload→OCR→Grading→Done) + 250ms elapsed ticker + real XHR upload progress + calibrated hints ("typically 2–4 min on this device", grade-stage flip at 150s) + honest caveat line ("Live stage updates are available in the paired mobile app. Here, stages follow typical on-device timing") [VERIFIED: index.html:569]. Completion, error, timeout (10-min XHR ceiling [VERIFIED: index.html:993,1022]), and `Finished in …` from real `processing_time_ms` are all real.

**Phase 1 UX work (no backend contract change, no token-in-browser):**

1. Keep timed stages; add burst-aware copy: when `?burst=true`, swap hints to "burst: typically under a minute — tunnel + T4" and show `MODE` from `/health` (local-only vs hybrid) before the run starts.
2. Add queue-position honesty for batch: "Paper 3 of 12 · ~2 min left at burst pace" computed from rolling `processing_time_ms` average — arithmetic on real numbers, not fake progress.
3. Retry path that preserves work: on XHR timeout, point at the Papers queue (`GET /results/{job_id}` poll) instead of "retry" — the server may still finish (already hinted at index.html:1022; make it a button).
4. Do NOT: expose pairing tokens to the browser to unlock WS (widens R2 auth hole); invent finer-grained % (backend only emits 10/20/50 — any interpolation is fabrication); add EventSource/SSE polling endpoint (new surface; unnecessary — completion is already real via XHR + queue).

## Standard Stack (no changes — CONSTRAINTS lock)

| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| FastAPI / uvicorn | ≥0.110 / ≥0.52 | server | single-process, no workers change |
| httpx | ≥0.27.0 (already pinned) | async retrofit + Colab path | no new dep |
| requests | ≥2.31 | startup pre-flight only after retrofit | remove from hot path |
| pyngrok | notebook cell (Colab-side pip) | burst tunnel | not a server dep |
| Pillow + pillow-heif | ≥12.0 / ≥1.6.0 | resize/convert | tuning knobs live here |

No package legitimacy audit needed: **zero new packages proposed.** (`cloudflared` binary is an operator-side alternative transport, not a pip/npm dep.)

## Common Pitfalls (phase-specific)

1. **Lowering `num_ctx` for speed** — crashes glm-ocr (`GGML_ASSERT`, runner death + 10s restart) [CITED: ipynb-adjacent issue #16696]. Floor is 8192 for vision.
2. **Expecting async retrofit to cut single-grade time** — it won't; sell it as throughput + responsiveness (§3).
3. **Parallelizing papers against one Ollama** — breaks the sequential-VRAM rule; OOM on T4/laptop. Batch = back-to-back.
4. **Auto-keep-alive / 24-7 Colab** — ToS breach + CONSTRAINTS-adjacent; attended burst only.
5. **Trusting Colab `percentage`/legacy `marks`** — server recomputes percentage [VERIFIED: main.py:436-439]; adapter coerces legacy types [VERIFIED: main.py:739-759]. Keep both.
6. **Stale tunnel URL 500s** — health-gate + circuit breaker (§2c), never a 600s hang per grade.
7. **WS token in browser localStorage** — trades R5 fix for R2 hole; web keeps timed stages.

## Validation Architecture

- Mock-first (no GPU): existing 19 adapter tests + new tests for health-gate/circuit-breaker state machine and `?burst=true` routing matrix (local-only / hybrid-healthy / hybrid-dead) via monkeypatched `_ollama_generate` / `httpx.AsyncClient` (pattern already proven in tests/test_colab_adapter.py [VERIFIED]).
- Timed runs (Wave-gated): single-paper `processing_time_ms` before/after tuning sweep; 2-concurrent overlap proof for async retrofit; N-paper batch wall-clock for burst-warm; `ollama ps`-empty check post-batch.
- Accuracy gate: every tuning combo re-runs Phase 3 eval subset (marks ±2) before adoption.

## Assumptions Log

| # | Claim | Risk if wrong |
|---|-------|---------------|
| A1 | CPU-bound magnitudes in §1b ladder (20–40% etc.) | Sweep finds smaller wins; Colab-first strategy covers the target anyway |
| A2 | T4 burst pace ≈ 45s/paper | Throughput math shifts; measure on first live burst session |
| A3 | `cloudflared` runs cleanly in Colab free runtime as ngrok alt | Fall back to pyngrok (already working); 1-task smoke test |
| A4 | Idle ≈ 90 min / session ≤ 12h (observed, not published) | Design already treats Colab as ephemeral; only copy changes |
| A5 | Threadpool (`to_thread`) acceptable at teacher scale | If dozens concurrent, revisit option B (httpx rewrite) |

## Open Questions

1. Actual GPU presence — answered by Wave 0 §1a procedure (10 min), not by more research.
2. Whether `?burst=true` should also skip local entirely when Colab healthy (yes, recommended) vs race both (rejected: VRAM + complexity) — planner decides, default to skip-local.
3. Notebook new-schema upgrade vs adapter-only — recommend: adapter-only for Phase 1 (works today), notebook schema + `/health loaded` flags as a stretch task.

## Sources

- Primary: `main.py` (inference §677-845, routes §349-474), `start.py` (pre-flight §83-100), `templates/index.html` (staged UI §938-1033), `Inscrona_Colab_Remote_Inference.ipynb` (server cells), `tests/test_colab_adapter.py`, PROGRESS.md timings, CONTEXT/ARCHITECTURE/RISKS/STACK/RISKS-R1-R5.
- Docs [CITED]: docs.ollama.com (GPU support, Windows reqs, FAQ num_ctx), httpx async docs, Colab FAQ (limits/ToS).
- Community [CITED, needs measurement]: ollama#16696 (glm-ocr num_ctx floor), ollama#17375 (Windows CUDA discovery), ollama#9704 (`ollama ps` proof), glm-ocr optimization guide (repeat penalty, JPEG-85/LANCZOS, generate-vs-chat endpoint note).

## RESEARCH COMPLETE

Ranked build order for the planner:

1. **Wave 0 — GPU proof (§1a) + async retrofit (§3A `to_thread`).** 10-min measurement gates everything; retrofit unfreezes the loop for all later work. Verify: `ollama ps` reading in PROGRESS.md; 2-concurrent overlap test.
2. **`?burst=true` + health-gate + circuit breaker (§2b-rotation, §2c).** Makes burst reachable (today it fires only on local failure) and stale-tunnel-safe. Verify: routing matrix tests (mocked) + live `MODE: hybrid` log.
3. **OCR tuning sweep (§1b ladder, `num_ctx=8192` floor first).** Only if Wave 0 shows CPU-bound local matters; else take only JPEG/edge wins and move on. Verify: 18-run table + eval-delta.
4. **Burst-warm batch mode (§4).** Prime + back-to-back + zero-resident unload proof. Verify: N-paper wall clock + post-batch `ps`-empty.
5. **Perceived-speed UX (§5).** Burst-aware copy, MODE badge, batch ETA from real averages, timeout→queue-poll retry button. Verify: headless render + copy review (no fake progress).
6. **Stretch:** notebook new-schema `/grade` + richer `/health`; `cloudflared` smoke test; `/api/health` fast-path (no sync Ollama probe).
