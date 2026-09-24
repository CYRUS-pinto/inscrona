# Inscrona Roadmap — photo → verified marks, teacher-fast, zero budget

Goal: a teacher photographs an answer sheet and gets verified marks as fast as
possible, with a verification workflow that never makes her wait or suffer.
Constraints: FastAPI-only, Ollama-only (`glm-ocr` + `llama3.2:3b`), local-FS
storage, no new framework/service/dependency without a BLOCKED entry + approval
(see CONSTRAINTS.md). Every DONE needs real command output in PROGRESS.md.

### Phase 0: Fix-and-verify web playground
Status: Executed. Playwright-grade proof: headless Chrome render shows
"Server live", Papers count 23, queue populated, donut/inspector render.
Shipped: truncated-script-tail restore, `mq` definition, boot block, fetch
timeouts, results key-mapping, server-side percentage. (Commits 6ee14d6.)

### Phase 1: Colab burst + speed (CURRENT)
Goal: p50 single page < 90s local, < 45s on Colab burst; waiting never feels dead.
Scope: local OCR tuning sweep (measured), `?burst=true` warm-batch mode,
Colab burst routing hardening (schema adapter DONE in 01769ef, health-checked
routing, circuit breaker), perceived-speed UX (staged progress copy, elapsed
ticker, honest timing notes). No model swap, no new deps.
Depends on: Phase 0.

### Phase 2: Teacher verification workflow
Goal: flags-first review, one-click corrections, submittable export.
Scope: low-confidence-first queue sort + filter chips, per-question flag
buttons persisted to result JSON, editable marks with server-side recompute +
`teacher_override`/`verified` fields, CSV `teacher_marks,verified` columns,
multi-file batch queue with "review flagged first" CTA, datalab-grade polish
(motion 150–250ms, skeleton shimmer, empty states, aria-live).
Depends on: Phase 0.

### Phase 3: Eval harness (accuracy gate)
Goal: every speed/UI change proves it didn't make grading dumber.
Scope: 10–15 golden pages with human marks, `eval.py` (shape, percentage
identity, transcript non-empty, marks ±2, concept keywords), markdown reports
in `./results/eval_*.md`, run-before/after discipline in README.
Depends on: Phase 0. Feeds: Phase 1 tuning choice.

### Phase 4: Deploy + packaging
Goal: zip → grading in < 10 min, URL stable for a class period.
Scope: harden `start.py` (QR for LAN IP, `--port`, `--burst-warm`,
Tailscale-detect), tunnel story (localtunnel default, Tailscale stable,
Pinggy/cloudflared as known-bad notes), operator README + `.env.example`.
Depends on: Phases 0–2.

### Phase 5: Mobile pairing polish
Goal: Expo app pairs in < 60s and mirrors web results.
Scope: fix pairing bootstrap (POST /api/pair without auth, rate-limited),
`/api/grade` GradeResult shape parity, WS token in client URL, offline queue.
Depends on: Phases 0 + 4. Needs user: Expo login for `eas build`.

### Phase 6: Accounts / multi-teacher / cloud
Status: Parked. Needs explicit user go/no-go (violates CONSTRAINTS.md as-is).
Teacher logins, class management, Postgres/auth, hosted GPU, BGE ensemble.
DO NOT START without constraint amendment.
