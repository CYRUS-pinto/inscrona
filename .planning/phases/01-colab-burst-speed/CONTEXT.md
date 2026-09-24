# Phase 1 CONTEXT — Colab burst + speed (locked decisions)

## User decisions (from overnight brief — user asleep, do not re-ask)
1. Speed is the top priority: teachers must not wait ~4 min/page. Target p50
   < 90s local, < 45s on Colab burst.
2. Google Colab free-GPU burst is approved as the speed path (hybrid router:
   local-first offline default, Colab burst/opt-in). Interactive-attended use
   only — never 24/7 headless serving (ToS).
3. No new frameworks, services, models, or dependencies (CONSTRAINTS.md).
   `google-colab-cli` may be prepared in WSL but Windows can't run it.
4. "The user should never suffer": perceived speed matters as much as real
   speed — staged progress, elapsed ticker, honest timing copy, no
   spinner-forever, retry paths that preserve work.
5. Verification-before-completion: every task ends with a runnable `<verify>`
   command and real output. Mock-first tests (no GPU) for logic; timed runs
   for numbers.

## Already shipped (do not replan)
- `_normalize_colab_result` legacy→GradeResult adapter + 5 mocked tests
  (`tests/test_colab_adapter.py`, green).
- Minimal `.env` loader (stdlib-only) in `main.py` + `start.py`; non-fatal
  `check_colab()` printing `MODE: local-only|hybrid` (commit 01769ef).
- Deleted dead `_colab_generate` NotImplementedError stub.

## Known facts for planning
- Measured: local `glm-ocr` 177–231s/page, `llama3.2:3b` grading 24–42s.
  `ollama ps` currently shows no loaded models (keep_alive=0 discipline works).
- `nvidia-smi` is NOT installed → likely CPU-only laptop; local floor may be
  unfixable without Colab. Confirm GPU presence as Wave 0 task.
- `_ollama_generate` uses blocking `requests.post` inside `async def`
  (event-loop freeze ~4 min). `httpx` is already a dependency.
- `_colab_grade_endpoint` exists; Colab notebook exists
  (`Inscrona_Colab_Remote_Inference.ipynb`) but its `/grade` returns
  old-schema keys (adapter now covers this server-side).
- Web playground proven green (headless render: Server live, 23 papers).
- `GET /results` re-parses all JSONs per request; fine at 23, watch at scale.
