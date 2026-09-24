# Phase 1 PLAN — Colab burst + speed (overnight autonomous run)

**Goal:** p50 single page < 90s local, < 45s on Colab burst; waiting never feels dead.
**Constraints:** CONSTRAINTS.md is binding — FastAPI-only, Ollama-only (`glm-ocr` + `llama3.2:3b`),
local-FS only, NO new dependency (pip/npm/binary-as-dep). New query params / in-module
globals are allowed (not dependencies). Every task ends DONE (real command output in
PROGRESS.md) or BLOCKED (exact error). Do NOT edit product code beyond the files listed per task.
**Interpreter (binding):** every `python` command below means `C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe`
run from the repo root. Bare `python` resolves to system Python 3.13 without project deps (`pytest` collection
fails with `ModuleNotFoundError: pillow_heif`); the venv is Python 3.11 with all deps installed (5 tests collect).
**Build order:** follows RESEARCH.md ranked order (§Wave 0 → async → burst routing → tuning → warm → UX),
with two documented deviations: (a) `?burst=true&warm=1` query params on existing `POST /grade`
instead of a new `POST /api/burst-warm` route — smaller surface, same behavior; (b) no new
`POST /api/colab-url` endpoint — URL rotation handled via existing `check_colab()` + per-request
health gate, operator pastes URL into `.env`.
**Already shipped — do not rebuild:** `_normalize_colab_result` + 5 tests (`tests/test_colab_adapter.py`,
stdlib `.env` loader + `check_colab()` (`main.py`, `start.py`), dead `_colab_generate` deleted.

## Wave 0 — GPU proof gate (decides local-vs-Colab emphasis; all later tasks read its verdict)

### Task 0: Prove CPU-vs-GPU, record the verdict that gates Wave 2 scope

**Goal:** Authoritative answer to "does this laptop have a usable NVIDIA GPU for Ollama?"
written to PROGRESS.md, so the tuning sweep (Task 3) knows whether to run full or cheap-wins-only.
**Files to modify (all git-tracked, verified via `git ls-files`):** none (read-only probes) + append
verdict to `PROGRESS.md` — check `git ls-files | Select-String PROGRESS` first; if PROGRESS.md is
untracked, create it (it is the CONSTRAINTS-mandated execution log, not product code).
**Steps:**
1. `Get-Command nvidia-smi; nvidia-smi -L 2>&1`; if absent, also try
   `"$env:ProgramFiles\NVIDIA Corporation\NVSMI\nvidia-smi.exe" -L` (driver may exist without PATH).
2. Start the server (`C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe start.py` from the repo root), run one live `/grade` on a fixed sample page, and during
   inference run `ollama ps` — record the `PROCESSOR` column (`100% CPU` vs `100% GPU`).
3. Search `%LOCALAPPDATA%\Ollama\server.log` for the `inference compute` line for that run;
   record `library=cuda` vs `library=cpu`.
4. Run `ollama show glm-ocr`, `ollama list`; record one `/grade` `processing_time_ms`.
5. Apply RESEARCH §1a decision rule and append a verdict block to PROGRESS.md:
   `VERDICT: CPU-only | GPU-usable`, the four readings above, and one line:
   `Task-3 scope: FULL sweep | CHEAP-WINS-ONLY (edge 1600 + JPEG 75, no 18-run grid)`.
   If GPU exists but Ollama picks CPU, do NOT fix drivers in code — record operator remedies
   (driver ≥ 551.61, `OLLAMA_LLM_LIBRARY` override) as a BLOCKED-note for the human, continue as CPU-only.
**<verify>:** `ollama ps; if ($?) { Select-String -Pattern 'inference compute' "$env:LOCALAPPDATA\Ollama\server.log" | Select-Object -Last 3 }; Select-String -Pattern 'VERDICT' PROGRESS.md`
**<fails_when>:** `VERDICT` line missing from PROGRESS.md, or no `PROCESSOR` reading captured during a
live grade (exit non-zero / empty match = gate not proven, STOP the phase, do not guess).
**Rollback:** no code changed; delete the verdict block only if a reading is later proven wrong, re-run probes.

## Wave 1 — Tracer (one production-quality end-to-end slice, mocked Colab, verified before expansion)

### Task 1 (tracer): Async retrofit + `?burst=true` health-gated burst routing for a single grade

**Goal:** One paper grades end-to-end through the full stack with (a) a free event loop during the
~4-min inference window and (b) burst reachable on demand (today Colab fires only on local failure).
This is the slice every Wave 2 task builds on — production-quality, no stubs.
**Files to modify (git-tracked):** `main.py`, `tests/test_colab_adapter.py` (extend in place — no new
test file, keeps every touched path `git ls-files`-visible).
**Steps:**
1. Async retrofit, RESEARCH §3 option A (documented: ~4-line diff, keeps streaming/parse logic;
   option B httpx rewrite is the fallback only if overlap proof fails): in `main.py`, wrap the two
   blocking calls in `_grade_with_fallback` (`main.py:802` `ocr_text = _ollama_generate(...)`,
   `main.py:806` grade call) with `await asyncio.to_thread(...)` (`asyncio` already imported,
   `main.py:11`). Leave `_ollama_generate`'s `requests` streaming body untouched; leave
   `_broadcast_progress` fire-and-forget as-is (RESEARCH §3 risk note). Do NOT touch
   `GET /api/health`'s sync probe in this task (stretch item, Task 4 only if free).
2. Burst opt-in on the existing route only: `POST /grade?burst=true` means — health-gate Colab
   first via `GET {COLAB_INFERENCE_URL}/health` with a SHORT timeout (5–8s, new constant, never
   the 600s grade timeout); if healthy → Colab primary via existing `_colab_grade_endpoint`
   (`main.py:762`) + `_normalize_colab_result` (`main.py:719`), skipping slow local OCR; if
   unhealthy/empty URL → local path unchanged with flag `burst_unavailable` and log line
   (degrades to local-only, never a 500). Default (no param) keeps today's local-first behavior
   (offline-safe default preserved). Skip-local-on-healthy (not racing): documents RESEARCH open
   question 2 — racing violates the sequential-VRAM golden rule.
3. Extend `tests/test_colab_adapter.py` (mock-first, proven pattern — monkeypatch
   `_ollama_generate` / `httpx.AsyncClient`, no GPU): routing matrix local-only / hybrid-healthy /
   hybrid-dead; health-probe timeout path asserts fail-fast (no 600s hang — assert with a short
   wall-clock bound); `burst_unavailable` flag + `GradeResult` validation on every burst path
   (percentage still recomputed server-side, `main.py:436-439`).
4. Overlap proof (mocked inference, no GPU): two concurrent `POST /grade` with `_ollama_generate`
   stubbed to `sleep 20` — wall clock must be ~20s overlapped, not ~40s serialized. Record numbers
   in PROGRESS.md honestly (single-grade p50 does NOT move here — throughput/responsiveness only).
**<verify>:** `C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe -m pytest tests/test_colab_adapter.py -q` (all green incl. new routing tests)
AND `C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe -m pytest tests/test_colab_adapter.py -q -k "overlap or routing or burst"` passes with
the overlap wall-clock line visible in output.
**<fails_when>:** any test red; or overlap run shows serialized (~2× single) wall clock (retrofit ineffective);
or `?burst=true` with dead URL returns 500 instead of local-fallback + `burst_unavailable`.
**Rollback:** `git diff main.py` is the whole change — `git stash` / `git checkout -- main.py` restores;
tracer must be green before ANY Wave 2 task starts; if red at dawn, revert and leave Phase 0 behavior.

## Wave 2 — Expansion (parallel-safe: Task 2 and Task 4 touch disjoint files; Task 3 follows in Wave 3 — same-file rule)

### Task 2: Circuit breaker + burst-warm batch mode (back-to-back, zero-resident unload proof)

**Goal:** A dead tunnel can never add its 600s timeout to a grade again, and an N-paper burst runs
warm back-to-back within the sequential-VRAM golden rule (`keep_alive=0` everywhere, unchanged).
**Files to modify (git-tracked):** `main.py`, `tests/test_colab_adapter.py`.
**Steps:**
1. Module-global circuit state in `main.py` (stdlib only): `CLOSED → OPEN` after N=3 consecutive
   Colab failures (timeout/5xx/parse); half-open probe after 60s cooldown; while OPEN, skip Colab
   instantly (fail-fast to local) and surface `mode` (`local-only|hybrid`, reusing the `check_colab()`
    verdict at request time) plus `colab_circuit_open` in the `GET /health` payload and result
   `flags`. Counts reset on success. No persistence (in-memory like `PAIRING_TOKENS` — restart
   resets to CLOSED, document in a comment).
2. Burst-warm via query params on the existing route — `POST /grade?burst=true&warm=1`: on first
   paper, after the Task 1 health gate succeeds, prime by hitting notebook `/health` (confirms tunnel
   + models present — "warm" means session verified, NOT `keep_alive>0`; never set keep-alive).
   Papers run back-to-back exactly as today (OCR `keep_alive=0` → grade `keep_alive=0`, `main.py:802/806`
   pattern); server stays stateless per paper (`results/{job_id}_grade.json` per paper is the batch
   record); the web UI loops its existing single-file call N times (no server queue — CONSTRAINTS
   forbids Redis/BullMQ). End-of-batch discipline: after last paper (or batch abort — best-effort
   documented limitation, NOT retried server-side), issue unload
   `POST /api/generate {"model": <name>, "keep_alive": 0}` for both models against the Colab daemon
   and log the post-batch empty check.
3. Mock-first tests in `tests/test_colab_adapter.py`: breaker state machine (3 failures → OPEN,
   instant-skip while OPEN with `colab_circuit_open` flag, half-open probe after cooldown, reset on
   success); warm-prime call asserted before first paper; unload `keep_alive: 0` calls asserted
   post-batch. Timed N-paper wall-clock (mocked) + post-batch empty-check line recorded in PROGRESS.md.
**<verify>:** `C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe -m pytest tests/test_colab_adapter.py -q` green AND
`C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe -m pytest tests/test_colab_adapter.py -q -k "circuit or warm or breaker"` shows the OPEN/half-open
transitions passing.
**<fails_when>:** breaker never OPENS after 3 mocked failures; or a mocked-dead tunnel grade hangs near
600s instead of failing fast; or post-batch unload calls missing from the mocked call log.
**Rollback:** single-file `main.py` hunk + test additions — `git checkout -- main.py` restores
pre-breaker routing (Task 1 behavior); breaker defaults CLOSED so partial work degrades to Task 1.

### Task 4: Perceived-speed UX — burst-aware copy, MODE badge, honest batch ETA, timeout→queue retry (runs parallel with Task 2 — disjoint files)

**Goal:** "The user never suffers" (CONTEXT D-4): staged progress, elapsed ticker, honest timing copy,
no spinner-forever, retry that preserves work — with zero fake progress and no WS-token-in-browser
(RESEARCH §5 pitfall 7 — the WS pairing-token gate stays, web keeps timed stages).
**Files to modify (git-tracked):** `templates/index.html` ONLY — the `mode` badge field on `GET /health`
is added by Task 2, which owns `main.py` in this wave. This task MUST NOT touch `main.py` (same-file
parallel-edit rule); `GET /api/health` sync probe untouched.
**Steps:**
1. When `?burst=true`: swap hint copy to burst pacing ("burst: typically under a minute — tunnel + T4")
    and show a `MODE` badge (`local-only` vs `hybrid`) read from `/health` BEFORE the run starts
    (field provided by Task 2 in this wave; if absent, render `local-only` and record a
    BLOCKED-dependency note — do NOT edit `main.py` from this task).
2. Batch ETA from real numbers only: "Paper 3 of 12 · ~2 min left at burst pace" computed from the
   rolling `processing_time_ms` average of completed papers in the batch — arithmetic on measured
   values; keep existing timed stages (Upload→OCR→Grading→Done), 250ms ticker, real XHR progress,
   calibrated local hints ("typically 2–4 min on this device", 150s grade-stage flip), 10-min XHR
   ceiling, and the honest caveat line (all verified existing, `templates/index.html:938-1033`) —
   do NOT invent finer-grained % (backend emits only 10/20/50) and do NOT add SSE/polling endpoints.
3. Timeout path preserves work: on XHR timeout, replace bare "retry" with a button that polls the
   Papers queue (`GET /results/{job_id}`) — the server may still finish; never resubmits blindly
   (mobile-style triple-submit of a 4-min job is the anti-pattern, RISKS.md R8).
**<verify>:** `C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe -c "import urllib.request; h=urllib.request.urlopen('http://127.0.0.1:8000/').read().decode(); assert 'MODE' in h.upper() or 'mode' in h, 'badge missing'; assert 'burst' in h.lower(), 'burst copy missing'; print('UX copy present')"` with the server started first via `Start-Job { C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe start.py }` from the repo root (stop the job afterwards)
AND `Select-String -Pattern '(typically (2–4 min|under a minute)|Paper \d+ of|poll.*queue|local-only|hybrid)' templates/index.html` returns the copy lines.
**<fails_when>:** headless fetch missing burst/MODE strings; or any interpolated % finer than backend
10/20/50 stages found in the diff (fabrication); or a pairing token/`localStorage` token appears in
the web UI (auth-hole regression — instant revert).
**Rollback:** `git checkout -- templates/index.html`;
Phase 0 timed-stages UI is the intact fallback. (`GET /health` changes belong to Task 2 — revert there.)

## Wave 3 — OCR tuning sweep (runs AFTER Task 2 — same `main.py` knob region; scope set by Wave 0 verdict)

### Task 3: Measured OCR tuning sweep with `num_ctx=8192` floor + eval-delta adoption gate

**Goal:** The only legitimate local-latency win, measured not guessed — adopt a combo only if it is
faster AND grading stays within marks ±2 on the eval subset.
**Files to modify (git-tracked):** `main.py` (request-level `options` dicts + resize/JPEG/prompt knobs
only — `main.py:691`, `main.py:74`, `main.py:385/399`, `main.py:291-303`), `PROGRESS.md` (results table).
**Steps:**
1. FIRST set `num_ctx=8192` for the `glm-ocr` call (stability floor — RESEARCH §1b pitfall 1:
   default 4096 crashes vision on table-heavy images; larger ctx is a correctness fix, not a speedup).
2. FULL scope (only if Wave 0 verdict = GPU-usable): grid longest-edge {2000, 1600, 1280} × JPEG
   {90, 75} × OCR prompt {full ~200-word `OCR_PROMPT`, terse "Transcribe all visible text, preserve
   question numbers and layout."} on 3 fixed pages = 18 timed runs as an UNATTENDED batch
   (~3 min each on CPU — never interactive); record `processing_time_ms` + transcript length per cell.
   CHEAP-WINS-ONLY scope (Wave 0 = CPU-only): single comparison 2000/q90/full vs 1600/q75/terse on
   the same 3 pages (6 runs), then stop — do not burn the night proving an unfixable floor.
3. Grading `num_predict` 2048 → 1024 in the same pass (grading output is one JSON object ~300–600
   tokens; 3–4× headroom today — predicted 5–10% off the 24–42s stage).
4. Adoption gate: every candidate combo re-runs the Phase 3 eval subset shape (transcript non-empty,
   marks ±2, concept keywords) — adopt the fastest passing combo; record the full table + adopted
   combo + eval deltas in PROGRESS.md. Ladder order (edge → JPEG → prompt → caps) is highest-impact-first.
**<verify>:** `Select-String -Pattern 'processing_time_ms|transcript.*len|eval.*±2|ADOPTED' PROGRESS.md`
shows the results table AND `C:\Users\Cyrus\.hermes\hermes-agent\venv\Scripts\python.exe -m pytest tests/test_colab_adapter.py -q` still green
(no contract drift from knob changes).
**<fails_when>:** results table missing any of (combo, `processing_time_ms`, transcript length); or an
adopted combo lacks its eval-delta line (gate skipped); or `num_ctx` for glm-ocr reads below 8192
after the change (floor violated).
**Rollback:** knob-only hunk in `main.py` — `git checkout -- main.py` restores 2000/q90/full/2048
baselines; the PROGRESS.md table survives as evidence regardless.

## Threat-model note — Colab URL handling (tunnel URL in env/logs, PII in transit)

- **Tunnel URL = bearer secret.** `COLAB_INFERENCE_URL` (ngrok or cloudflared) is a capability URL:
  anyone holding it can POST images for grading on the teacher's Colab GPU and, via legacy-schema
  responses, move student PII. Store ONLY in `.env` (never committed — verify `.gitignore` covers
  `.env` before writing; the stdlib loader reads process env, no dotenv dep). `check_colab()` log
  lines print `MODE: hybrid` and MUST NOT print the URL (truncate to host hash or last 8 chars).
  Per-request health failures log `colab unreachable` without echoing the URL (URLs also land in
  exception tracebacks — the breaker path in Task 2 catches timeout/5xx/parse and logs a fixed
  string, never `str(exc)` containing the URL).
- **Stale-URL fail-closed.** Rotation every session is assumed: health gate (Task 1, 5–8s) + circuit
  breaker (Task 2, 3-strikes/60s) mean a stale URL degrades to local-only with `burst_unavailable` /
  `colab_circuit_open` flags — never a 600s hang, never a 500 with the URL in the body.
- **PII in transit.** Grade images + OCR text (student names/reg-nos, CONTEXT-verified) travel
  laptop→tunnel→Colab and back over TLS (pyngrok `bind_tls=True`; cloudflared equivalent). Server-side
  mitigations already locked: percentage recomputed locally (never trust Colab arithmetic), legacy
  `marks` coerced via adapter, `ocr_text` default `""` on passthrough. Attended-use only (teacher's
  own session, one class period, tab open — never 24/7, never shared across teachers, per CONTEXT D-2);
  no keep-alive pings, no auto-reconnect bots. No new telemetry: Sentry already carries PII risk
  (RISKS.md R9) — burst code paths add no new Sentry events.
- **Out of scope (explicitly NOT in this phase):** R2 open-web grading/auth inversion, R6 CSV injection,
  WS token reachability (R5) — parked for Phases 2/4; Task 4 is forbidden from trading the R5 fix for
  an R2 hole (no token in browser).

## Execution order & dawn acceptance

Wave 0 (Task 0) → Wave 1 (Task 1 tracer; BLOCKS all else) → Wave 2 (Task 2 ∥ Task 4) → Wave 3 (Task 3).
Dawn acceptance: `pytest` green, PROGRESS.md holds (GPU verdict, overlap numbers, breaker transitions,
tuning table + ADOPTED combo, UX copy proof), `git log --oneline` shows one commit per task, and no
commit adds a line to `requirements.txt` (`git diff --stat requirements.txt` empty — dependency gate).
