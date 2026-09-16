# Inscrona — Project Notes & Decision Log
(Everything discussed and decided across this conversation, in order of relevance)

---

## 1. Project Identity & Goal

- **Name:** Inscrona (originally called "Inscora" / "GradeAI" in your older, larger spec)
- **What it is:** AI-powered exam/answer-sheet correction platform for teachers — OCR the handwritten answer, structurally analyze the paper (sections/questions/marks), grade against an answer key, produce a score + feedback.
- **Deployment targets:**
  - Your personal consumer laptop (dev/testing) — assume 8–12GB VRAM GPU (RTX 3060/4060-class).
  - A college server later — **hardware not yet confirmed**, but assumed to be *at least as capable* as your laptop. Your working rule: **if it runs well on your consumer hardware, it will run on the college's hardware too.**
- **Timeline (evolved over the conversation):** "done tonight" → "done by Sunday night" → "as fast as possible, but Sunday is the hard deadline."
- **Old spec status:** You have a much larger, "$10M-tier" production spec (auth, multi-tenant DB, native mobile apps, full observability stack, 9 build phases). You explicitly said: **fresh start, no linking to old files** — the *tech choices* from that spec (models, design tokens, ensemble weights) are still useful reference, but the architecture/phasing is not being followed as-is right now.

---

## 2. The Golden Rule (locked, non-negotiable)

**Run AI models sequentially, never simultaneously**, to avoid VRAM Out-Of-Memory crashes on consumer hardware:

```
Load OCR/vision model → extract text → unload it (Ollama keep_alive: 0)
→ load grading LLM → evaluate against rubric → unload it
```
You confirmed this explicitly after an earlier draft glossed over it — this is the core architectural constraint everything else is built around.

---

## 3. AI Model Stack (finalized)

| Role | Model | Why |
|---|---|---|
| OCR / Vision | **GLM-OCR** (0.9B params) | Your research found Chandra OCR-2 (Qwen3.5-2.5B base) was good, but an industry contact specifically recommended GLM-OCR over it. Scores ~94.62 on OmniDocBench, handles tables and math/LaTeX well, small footprint. |
| Grading / Reasoning | **Llama 3.2:3B** (or DeepSeek-R1-Distill-1.5B as alternate) | Originally considered DeepSeek-R1-Distill-Qwen-7B, but downsized for VRAM/KV-cache headroom on consumer GPUs. 1.5–3B range gives best throughput without OOM risk. |
| Serving engine | **Ollama** (not vLLM, not LM Studio) | vLLM requires building `transformers` from source (bleeding-edge ≥5.0/5.1) — fragile, prone to `ValidationError` crashes. LM Studio needs manual multimodal projector (`mmproj`) files for GLM-OCR and disabling flash-attention — more manual friction. **Ollama natively supports GLM-OCR with one pull command**, runs headless as a background service — which is exactly how it'll run on the college's (likely Linux) server, so your dev setup transfers with zero changes. |
| Layout/structure detection | PP-DocLayout (PaddleOCR) | Detects question numbers, section headers, marks annotations, diagram boxes, table regions — **not yet built for MVP**, deferred; for the weekend test you're manually cropping test papers instead. |
| Embeddings / semantic scoring | BGE-M3 + BGE-Reranker-v2-M3 | Part of the full ensemble grading design (below) — from the larger spec, not required for the bare-metal MVP test but is the intended next layer. |

**Not using:** vLLM, LM Studio (for production), Docker for the model layer, cloud APIs (OpenAI/Azure) — the older spec had a "CRITICAL BUG" note about workers calling paid cloud APIs; the rule is **zero tolerance for paid API calls** anywhere.

---

## 4. Known Bugs You Must Code Around

1. **GLM-OCR silent crash bug:** Images larger than ~2300×2300px cause the OCR server to silently drop the request — no error, no log. **Fix:** hard-resize every incoming image to a max of 2000px on its longest edge *before* sending to OCR.
2. **iOS HEIC format:** iPhones upload `.HEIC` by default; most Python vision pipelines error on it. **Fix:** use `pillow-heif` to convert to JPEG first. *(You confirmed this is already handled on your end.)*
3. **VRAM/KV-cache blowup:** Long exam text pushed into a 7B+ model's context can consume 2GB+ of VRAM just for KV cache per sequence — this is why the grading model was downsized to 1.5B–3B rather than 7B.
4. **vLLM + GLM-OCR dependency hell:** Requires a from-source `transformers` build; avoided entirely by using Ollama instead.

---

## 5. Backend (MVP scope)

- **Framework:** Python **FastAPI**, running **synchronously** (no Celery/BullMQ/queues for the weekend build — that's deferred to the full production spec).
- **Storage:** **Local filesystem only** for now — `./uploads/` for images, `./results/{id}_grade.json` for output. No Postgres/MinIO/Redis in the MVP (those exist in the long-term spec only).
- **Structured output:** Use a Pydantic schema + Ollama's `guided_json`/`response_format` so the LLM's output is constrained to valid JSON matching your intended DB shape — avoids parsing errors, makes it storage-ready later.
- **Testing without extra tools:** FastAPI's built-in Swagger UI (`/docs`) is enough to manually upload a test image and check the pipeline — no need for Postman/Bruno for the MVP.
- **Logging:** **Loguru** for local, color-coded terminal logs — chosen over Sentry for the weekend build since Sentry's instrumentation for local LLM calls would eat into build time.

---

## 6. Frontend (design system — "Stitch" tokens, from the larger spec, still valid)

- **Framework:** Next.js 14 + Tailwind CSS.
- **Theme:** Dark mode by default. Background `#0a0a0a`, surfaces `#131313`/`#1c1c1c`, accent teal `#0d9488`.
- **Fonts:** Inter (UI text), JetBrains Mono (numbers — roll numbers, marks, confidence scores).
- **Touch targets:** Minimum 44×44px everywhere (mobile grading use case).
- **Confidence color coding:** green = auto-accept, amber = flag-for-review, red = failed/manual.
- Full token set (spacing, radius, shadow, transitions) exists in your original spec if you need to paste it back in later.

---

## 7. Networking (phone → laptop testing)

- **Tunneling tool chosen: Pinggy** (`ssh -p 443 -R0:localhost:8000 free.pinggy.io`) — zero install, no account, works over plain SSH, includes a terminal-based request inspector so you can debug failed uploads live.
- **Why not the alternatives:**
  - *Vercel* — can't work at all; it's serverless and can't reach your local GPU.
  - *Ngrok* — good inspector but stricter free-tier bandwidth limits, requires account + binary download.
  - *Cloudflare Tunnel* — unlimited free bandwidth and good for a **permanent** deployment later (real domain, no debugging need), but has no request inspector, so it's worse for *today's* debugging.
- **Cross-platform uploads:** Because teachers/students may be on **Windows, Linux, or Apple devices**, the plan is to serve a plain HTML upload page directly from FastAPI — anyone just opens the Pinggy/tunnel URL in any modern browser. No native app needed for this.

---

## 8. Coding Agents — what you considered and where it landed

| Tool | Verdict |
|---|---|
| **OpenCode** (CLI) | Chosen for **backend** work — terminal-level control, works with free API keys (75+ providers), critical for getting the exact Ollama sequential-loading logic right without GUI abstraction hiding the diff. |
| **Google Antigravity** (GUI app) | Chosen for **frontend** work — good at visual Next.js/Tailwind scaffolding. Has a CLI mode (`agy`) too, but you're using the full GUI app for frontend specifically. |
| **Roo Code / Cline** (VS Code extensions) | Flagged as the *safest* free-API-key option generally — they show a visual diff before applying any change, unlike CLI agents that edit files immediately. Good fallback if OpenCode gets unpredictable. |
| **OpenHands** | Considered and set aside — good for fully autonomous, unattended, whole-ticket work in a Docker sandbox (opens PRs by itself), but that independence is a liability when you need to closely supervise VRAM-sensitive local model sequencing. Better suited to later, larger, less time-critical work. |
| **YC's `qm`** | Checked and rejected for this project — it's a multiplayer/org-wide agent harness (Slack integration, per-employee workspaces, cloud deployment via Fly/AWS). Solves a team-collaboration problem you don't have; adds cloud account + infra setup with zero benefit to a solo weekend build. Revisit only if Inscrona becomes a multi-teacher, cloud-deployed product later. |
| **Dual-agent rule:** | Keep OpenCode and Antigravity in **strictly separate folders** (`./backend`, `./frontend`) — pointing two agents at the same files causes context collisions and overwritten work. This was explicitly flagged as a common mistake in tutorials that claim you can "safely mix" them in one workspace. |
| **`AGENTS.md` pattern:** | Put a strict context file in each folder telling the agent the exact architecture rules (endpoint shape, sequencing logic, design tokens) *before* it writes code — this keeps free-tier/smaller models from hallucinating the networking logic. |

---

## 9. Code Quality / Observability — what's deferred vs. what's active now

**Active now (MVP):**
- Loguru for terminal logs.
- FastAPI's `/docs` for manual testing.

**Deferred to post-MVP / college deployment:**
- **Sentry** — full Python SDK, initialized in FastAPI, but with `traces_sample_rate=0.1` to avoid overhead once you do add it.
- **CodeRabbit** — automatic PR review on GitHub, to catch logic bugs in AI-agent-generated code.
- **Glitchtip** — a lighter, Apache-2.0, Sentry-SDK-compatible self-hosted alternative, identified in your larger spec's observability tier (alongside Grafana + Loki + Tempo + Prometheus) — relevant once you're running the full production stack, not for tonight.

---

## 10. Grading Logic (from the full spec — reference for when you build past the bare pipeline)

- **6-metric similarity score (S):** cosine similarity (BGE-M3) 0.30, Word Mover's Distance 0.20, Jaccard 0.15, normalized edit distance 0.10, BLEU 0.15, ROUGE-L F1 0.10.
- **Final ensemble:** `Final = keyword(0.25) + S(0.35) + LLM_score(0.40)`.
- **Reranker step:** if final score lands between 0.40–0.60, run BGE-Reranker-v2-M3 to refine borderline cases.
- **Confidence thresholds** vary by doc type (printed vs. handwritten vs. diagram vs. mixed) — printed auto-accepts at ≥0.85, handwritten at ≥0.60, etc.
- **Optional-question logic:** if a student answers more questions than required ("attempt any N of M"), grade all, keep the best N, flag the rest as excluded (teacher can override).
- None of this is required for your bare-metal weekend test — it's the next layer once OCR→grade proves out.

---

## 11. What "done" looks like for the weekend MVP specifically

A single FastAPI service that:
1. Serves an HTML upload form reachable via the Pinggy tunnel from any phone/laptop browser.
2. Accepts an image, converts HEIC→JPEG if needed, resizes to ≤2000px.
3. Sends it to Ollama's GLM-OCR, extracts text, unloads GLM-OCR.
4. Loads the grading LLM (Llama 3.2:3B), feeds it the extracted text + a rubric prompt, gets back structured JSON (marks, confidence, feedback).
5. Unloads the grading model.
6. Saves the result to a local JSON file.

Everything past this (database, auth, multi-tenant, native mobile, full observability, diagram grading, subject plugins) is the **long-term direction**, not this weekend's target.

---

## 12. Reference-Only Material (from your old spec — NOT part of the active weekend build)

You said to treat the old spec as a fresh start architecturally, but a few concrete details from it are worth keeping on hand rather than losing:

**Test data (real student answer sheets, for validating OCR/grading once the pipeline works):**
```
C:\Users\Cyrus\Downloads\New folder (33)\New folder (32)\New folder\Main2\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\
```
60+ HEIC images (IMG_1225.HEIC–IMG_1280.HEIC). Backup copy at:
```
C:\Users\Cyrus\Downloads\ocr\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\
```

**Old spec/reference documents (for pulling details back out later if needed — not to be re-linked into the new build):**
| File | Purpose |
|---|---|
| `C:\Users\Cyrus\Documents\Obsidian Vault\carw.md` | Feature inventory + implementation plan + teacher workflow (4,672 lines) |
| `C:\Users\Cyrus\Documents\Obsidian Vault\carw2.md` | Features extracted from old GradeAI projects (124 lines) |
| `/c/Users/Cyrus/Downloads/INSORA/gradeai-v2/SPEC.md` | Complete spec v2 (484 lines) |
| `/c/Users/Cyrus/Downloads/INSORA/gradeai-v2/INSCORA_COMPLETE_SPEC.md` | Full build spec v1 (12,441 lines) |
| `/c/Users/Cyrus/Downloads/INSORA/gradeai-v2/INSCORA_MASTER_PROMPT.md` | Agent operating model (1,741 lines) |

**Old spec's tooling standards (worth reconsidering once you're past the MVP, not for tonight):**
- Testing: Vitest (unit/integration), Playwright (E2E)
- CI/CD: GitHub Actions (Lint → Test → Build → Push Docker → Deploy)
- Design: "Stitch MCP" for UI generation, dark SaaS theme
- Package manager: pnpm (not npm/yarn)
- Old spec's original 6-week phase roadmap (Core Engine → Answer Keys → Paper Intelligence → Multi-Pass OCR → Calibration → Diagrams → Subject Plugins → $10M UI → Production/Docker) — **this full sequence is the long-term direction, not what you're building this weekend.** Your actual near-term order is: bare pipeline → basic UI → then revisit this roadmap for the real college rollout.
- Old spec used **Fastify** (not FastAPI) and **Chandra-OCR-2** (not GLM-OCR) for the backend/OCR layer — both superseded by your current decisions (FastAPI + GLM-OCR via Ollama). Don't mix the two specs' assumptions together.

---

## 13. Still Unverified / Needs Your Own Testing

- Whether GLM-OCR via Ollama's HTTP API preserves LaTeX/math formatting as well as running it natively.
- Whether your college's Wi-Fi has client isolation that would block phone→laptop local connections (matters for real deployment, not for Pinggy since that tunnels over the public internet).
- Whether the 1.5B/3B grading model retains enough reasoning depth for college-level proofs/essays vs. the 7B — you were planning a side-by-side comparison on ~10–50 real exams.
- Whether Pinggy's free tier handles large (5MB+) uncompressed phone photo uploads without dropping the connection.
