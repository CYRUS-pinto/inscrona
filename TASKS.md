## Task 1: Confirm GLM-OCR runs via Ollama on a real image and produces readable text
Depends on: none
Definition of done: Run `ollama run glm-ocr` (or via Ollama CLI/API with an image input) on at least one real test image, and verify the command exits successfully with readable, non-garbled, non-repeating OCR text output recorded in PROGRESS.md.
Relevant context: Images larger than ~2300×2300px cause the OCR server to silently drop the request with no error or log — ensure the test image is resized to a max of 2000px on its longest edge before sending to OCR. If using iPhone sample sheets (.HEIC), convert to JPEG first. Test data is available at `C:\Users\Cyrus\Downloads\New folder (33)\New folder (32)\New folder\Main2\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\` (backup: `C:\Users\Cyrus\Downloads\ocr\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\`). Verify that the OCR text output does not produce garbage or repeated tokens.

**Status: COMPLETE** ✅ — Real command output recorded in PROGRESS.md. GLM-OCR successfully read a test answer booklet via Ollama HTTP API, producing clean, readable text with no garbled or repeated tokens.

---

## Task 2: Verify llama3.2:3b grading with structured JSON and sequential unloading via Ollama
Depends on: Task 1
Definition of done: Pull/run `llama3.2:3b` via Ollama API/CLI with extracted OCR text and a grading rubric prompt constrained to JSON format (`response_format` / `format="json"`), verify output parses as valid JSON with marks, confidence, and feedback, and confirm models are unloaded using `keep_alive: 0` (demonstrated by `ollama ps` showing no models remaining resident in VRAM). Real command output and `ollama ps` output must be recorded in PROGRESS.md.
Relevant context: Run AI models sequentially, never simultaneously, to avoid VRAM Out-Of-Memory crashes on consumer hardware: Load OCR/vision model → extract text → unload it (Ollama keep_alive: 0) → load grading LLM → evaluate against rubric → unload it. Use structured output (Pydantic schema + Ollama's format='json' / guided_json) so the LLM's output is constrained to valid JSON matching your intended storage shape (marks, confidence score, feedback) to avoid parsing errors.

**Status: COMPLETE** ✅ — Verified end-to-end in PROGRESS.md. glm-ocr ran (177.2s), unloaded with keep_alive: 0 (verified by empty `ollama ps`), then llama3.2:3b ran (41.7s) returning validated structured JSON (`marks`, `confidence`, `feedback`), and unloaded with keep_alive: 0 (verified by empty `ollama ps`).

---

## Task 3: Implement core FastAPI backend pipeline with local storage and sequential model execution
Depends on: Task 2
Definition of done: Start the FastAPI service (e.g. via uvicorn), send a real image (HEIC or JPEG) with rubric to the grading endpoint via curl/test script, verify HTTP 200 response with structured grade JSON, verify the uploaded image is stored in `./uploads/` and output is stored in `./results/{id}_grade.json`, and confirm both models unload (`keep_alive: 0`). Real execution command, response payload, and Loguru terminal logs must be recorded in PROGRESS.md.
Relevant context: Framework is Python FastAPI running synchronously (no Celery, Redis, or message queues). Storage is local filesystem only (`./uploads/` for images and `./results/{id}_grade.json` for output). Must enforce the Golden Rule of sequential model execution: Load OCR model → extract text → unload (`keep_alive: 0`) → load grading LLM → evaluate against rubric → unload (`keep_alive: 0`). Images larger than ~2300×2300px cause GLM-OCR to silently drop requests with no error — hard-resize every incoming image to a max of 2000px on its longest edge before OCR. Reuse `pillow-heif` for HEIC conversion. Use Loguru for local color-coded terminal logs. Constrain grading output with a Pydantic schema matching the intended DB shape.

**Status: COMPLETE** ✅ — Verified end-to-end in PROGRESS.md. FastAPI app with `GET /health` and `POST /grade` running on port 8000. Verified via curl: returned HTTP 200 with structured GradeResult JSON, saved `uploads/bda47996bb98.jpg` (639 KB) and `results/bda47996bb98_grade.json`, logged via Loguru, and confirmed both models fully unloaded with empty `ollama ps`.

---

## Task 4: Serve HTML upload and grading results UI from FastAPI following notion.design.md
Depends on: Task 3
Definition of done: Add a `GET /` route to the FastAPI application that serves the complete web UI implementing the design tokens from `notion.design.md`. Verify via `curl -s http://127.0.0.1:8000/` returning HTTP 200 with valid HTML containing the styled hero band, upload card, file input, rubric input, primary purple CTA button, active processing spinner, and result badge/display. Submit an upload form test and verify result rendering. Record curl command output, HTTP status, and HTML structure snippet in PROGRESS.md.
Relevant context: From PROJECT_NOTES.md: "the plan is to serve a plain HTML upload page directly from FastAPI — anyone just opens the Pinggy/tunnel URL in any modern browser. No native app needed for this." From notion.design.md: Hero band with deep navy `#0a1530` and on-dark text `#ffffff`; canvas `#ffffff`, surface `#f6f5f4`, hairline `#e5e3df`, ink `#1a1a1a`, charcoal `#37352f`; signature purple primary button `#5645d4` (pressed `#4534b3`, text `#ffffff`) with rectangular 8px corners (`rounded.md`), padding `10px 18px`; cards with 12px corners (`rounded.lg`), 1px solid `#e5e3df`, and diffuse drop shadow `rgba(15, 15, 15, 0.2) 0px 24px 48px -8px`; inputs with 8px corners, height 44px, and focus border `2px solid #5645d4`; pill badges (`rounded.full`, 9999px) for confidence using semantic colors (green `#1aae39` for auto-accept, orange `#dd5b00` for review, red `#e03131` for manual); typography using Inter (or Notion Sans fallback) for body and JetBrains Mono for numbers/scores. Because model sequencing takes ~2-3 minutes, provide an animated loading state with clear status feedback while processing.

**Status: COMPLETE** ✅ — Verified in PROGRESS.md. `templates/index.html` built, `GET /` returns HTTP 200, and `POST /grade` handles file uploads returning JSON results.

---

## Task 5: Expose FastAPI service via Pinggy SSH tunnel and verify remote end-to-end grading
Depends on: Task 4
Definition of done: Connect the Pinggy SSH tunnel via `ssh -p 443 -R0:localhost:8000 free.pinggy.io` (or with options like `-o StrictHostKeyChecking=no`), extract the generated public tunnel URL (https://*.free.pinggy.link), verify that `curl -s <tunnel_url>/` returns HTTP 200 with the HTML UI, and post an image upload with rubric through the public tunnel URL (`<tunnel_url>/grade`) to confirm end-to-end grading succeeds remotely over HTTPS. Log the assigned public tunnel URL, curl test command outputs, and the HTTP response in PROGRESS.md.
Relevant context: From PROJECT_NOTES.md: "Tunneling tool chosen: Pinggy (ssh -p 443 -R0:localhost:8000 free.pinggy.io) — zero install, no account, works over plain SSH, includes a terminal-based request inspector so you can debug failed uploads live." From PROJECT_NOTES.md §13: verify "whether Pinggy's free tier handles large (5MB+) uncompressed phone photo uploads without dropping the connection." Keep local FastAPI running on port 8000 while the tunnel is established.

**Status: COMPLETE** ✅ — Verified end-to-end in PROGRESS.md. Pinggy tunnel established (`tunnel_test.py`), public HTTPS URL verified (`GET /health` returned HTTP 200, `GET /` returned HTML UI with 200, and `POST /grade` returned HTTP 200 with structured JSON grade).

---

## Task 6: Validate OCR and grading pipeline on real student handwritten answer pages
Depends on: Task 5
Definition of done: Run the end-to-end grading pipeline on at least two actual handwritten student answer pages from the test dataset (e.g. `IMG_1226.HEIC` and `IMG_1227.HEIC`), passing a subject-relevant grading rubric for the questions written on those pages. Verify that GLM-OCR transcribes handwritten sentences accurately (not just printed template headings), Llama 3.2:3b outputs valid structured JSON evaluation referencing the student's actual handwritten content, and both models unload cleanly. Record the transcribed handwriting snippet, grading JSON response, and execution times in PROGRESS.md.
Relevant context: From PROJECT_NOTES.md §12: "Test data (real student answer sheets, for validating OCR/grading once the pipeline works): `C:\Users\Cyrus\Downloads\New folder (33)\New folder (32)\New folder\Main2\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\` (backup: `C:\Users\Cyrus\Downloads\ocr\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\`). 60+ HEIC images (IMG_1225.HEIC–IMG_1280.HEIC)." Note that `IMG_1225.HEIC` was the booklet cover page; subsequent sheets contain actual student handwriting. Remember to enforce the resize rule (max 2000px longest edge) and HEIC conversion. From PROJECT_NOTES.md §13: verify "whether the 1.5B/3B grading model retains enough reasoning depth for college-level proofs/essays" on real handwritten papers.

**Status: COMPLETE** ✅ — Verified end-to-end in PROGRESS.md. Tested `IMG_1226` and `IMG_1227` (both converted from HEIC and resized to max 2000px). Both returned HTTP 200 with structured JSON referencing specific student handwritten concepts (economic barriers, unique thinking, empathy, resilience, frugality). Results saved in `results/` and both models unloaded.

---

## Task 7: Refactor web UI in templates/index.html to strictly implement notion.design.md specifications, OCR transcript display, and confidence badge logic
Depends on: Task 6
Definition of done: Update `templates/index.html` (and `main.py` if needed to pass `ocr_text` in the response) so the UI strictly implements all tokens and components from `notion.design.md`:
1. Workspace card uses the exact diffuse drop shadow: `box-shadow: rgba(15, 15, 15, 0.2) 0px 24px 48px -8px;` and 12px corners (`border-radius: 12px`).
2. Primary submit button strictly uses `#5645d4` (pressed `#4534b3`), rectangular 8px radius (`border-radius: 8px`), white text, 44px minimum touch target.
3. Badges are true pill shapes (`border-radius: 9999px`) using Notion pastel tints: mint `#d9f3e1` with green text `#1aae39` (for confidence ≥0.80 / Auto-Accept), peach `#ffe8d4` with orange text `#dd5b00` (for confidence 0.60–0.79 / Review Needed), and rose/red `#ffebeb` with red text `#e03131` (for confidence <0.60 / Manual Check).
4. Correct grading display logic: evaluate badge on `d.confidence` percentage (not marks >= 70), and format marks clearly as `${d.marks} / 10` using `JetBrains Mono`.
5. Add an extracted OCR transcript section (using pastel-tinted card or drawer) so teachers can review the raw handwritten text extracted by GLM-OCR alongside the marks and feedback.
Verify by testing `GET /` with curl, verifying all design tokens (`#0a1530`, `#5645d4`, `rgba(15, 15, 15, 0.2) 0px 24px 48px -8px`, `9999px`, `#d9f3e1`, `#ffe8d4`) are present in `templates/index.html`, and verifying the page renders correctly in a browser. Record curl outputs and token verification in PROGRESS.md.
Relevant context: From `notion.design.md`: "Buttons render at 8px radius ({rounded.md}), inputs at 8px, cards at 12px ({rounded.lg}), and pill tabs and status badges at 9999px. Only tabs and badges are fully pill-shaped — every other interactive surface is a rectangle." "Signature purple voltage — #5645d4 reserved for the dominant 'Get Notion free' CTA, never decorative." "Live workspace mockup card embedded in the hero with a 24px diffuse drop shadow: rgba(15, 15, 15, 0.2) 0px 24px 48px -8px." Pastel card tints: peach `#ffe8d4`, rose `#fde0ec`, mint `#d9f3e1`, lavender `#e6e0f5`. From `PROJECT_NOTES.md`: "Confidence color coding: green = auto-accept, amber = flag-for-review, red = failed/manual." Note: `POST /grade` currently returns `{"marks": int, "confidence": float, "feedback": str}`. To show the OCR transcript in the UI, ensure `POST /grade` also returns `ocr_text` (or saves it in the grade result) so the client can display it.

**Status: COMPLETE** ✅ — Verified end-to-end in PROGRESS.md. `ocr_text` added to `GradeResult` and returned from `/grade`. Tested on `IMG_1226.HEIC`. All design tokens verified (`#0a1530`, `#5645d4`, `rgba(15, 15, 15, 0.2) 0px 24px 48px -8px`, `9999px`, `#d9f3e1`, `#ffe8d4`, `#793400`), collapsible OCR transcript drawer implemented, and confidence badge logic corrected.

---

## Task 8: Add past results history endpoint and Notion-styled submission list to UI
Depends on: Task 7
Definition of done: Implement a `GET /results` endpoint in FastAPI that scans the `./results/` folder and returns a list of previously graded submissions (including job id, marks, confidence, and timestamp). In `templates/index.html`, add a "Recent Graded Papers" section styled using `notion.design.md` comparison table specs (`border: 1px solid #e5e3df`, `rounded: 8px`, `border-bottom: 1px solid #ede9e4`), allowing a teacher to click any past submission to view its grade, feedback, and OCR transcript without re-running models. Verify with `curl -s http://127.0.0.1:8000/results` returning HTTP 200 with the list of existing graded jobs (e.g. `ea2defc2af3f`, `4bb99789c406`, etc.), and verify in PROGRESS.md with the curl command output.
Relevant context: From `PROJECT_NOTES.md` §5: "Storage: Local filesystem only for now — `./uploads/` for images, `./results/{id}_grade.json` for output." From `notion.design.md`: Use `comparison-table` (`backgroundColor: #ffffff`, `rounded: 8px`, `border: 1px solid #e5e3df`) and `comparison-row` (`border-bottom: 1px solid #ede9e4`) styling for table rows. Enables teachers to review and navigate previously graded submissions during an assessment session directly from the local JSON store without re-running the 2-minute inference pipeline.

**Status: COMPLETE** ✅ — Verified end-to-end in PROGRESS.md. `GET /results` endpoint returns array of graded jobs wrapped in `{"results": [...]}` with timestamp, marks, confidence, and feedback. JS fetch logic verified with live 8 results in DOM.

---

## Task 9: Run multi-paper sequential grading benchmark on 5 real student answer sheets
Depends on: Task 8
Definition of done: Run a benchmark script that submits 5 consecutive student answer sheets (`IMG_1226.HEIC` through `IMG_1230.HEIC`) to `/grade`, confirms all 5 return HTTP 200 with valid JSON results, verifies `ollama ps` returns 0 resident models after completion (proving zero cumulative VRAM leakage across multiple runs), and computes the average processing time per paper. Record the summary table of marks, confidence scores, latencies, and final `ollama ps` output in PROGRESS.md.
Relevant context: From `PROJECT_NOTES.md` §13: "you were planning a side-by-side comparison on ~10–50 real exams." From `PROJECT_NOTES.md` §2 & §4: The core Golden Rule is sequential model execution without OOM on consumer hardware; consecutive requests must cleanly load and unload models without accumulating resident VRAM or leaking GPU memory. Test data is in `C:\Users\Cyrus\Downloads\New folder (33)\New folder (32)\New folder\Main2\md\drive\Answer papers-20260425T192317Z-3-001\Answer papers\`. Verify that none of the 5 sheets trigger token looping or silent drops, and ensure the max 2000px resize rule is applied to every sheet.

**Status: COMPLETE** ✅ — Verified in PROGRESS.md via `bench_5.ps1`. 5/5 papers graded successfully with HTTP 200 and valid JSON. Total time 710.1s, average 142s per paper. `ollama ps` confirmed 0 resident models with GPU memory fully freed.

---

## Task 10: Add CSV grade export endpoint and Notion-styled export button to UI
Depends on: Task 9
Definition of done: Add a `GET /results/export.csv` endpoint in FastAPI that iterates over all saved `.json` files in `./results/`, parses their fields (`job_id`, `marks`, `confidence`, `status`, `feedback`, `timestamp`), and streams back a CSV file (`Content-Type: text/csv`). In `templates/index.html`, add an "Export CSV" button to the Recent Graded Papers section styled per `notion.design.md` `button-secondary` specs (`border: 1px solid #c8c4be`, `rounded: 8px`, `padding: 8px 14px`, `background: transparent`, `color: #1a1a1a`). Test via `curl -s http://127.0.0.1:8000/results/export.csv` returning HTTP 200 with valid CSV headers and rows. Record the curl command output and a sample CSV snippet in PROGRESS.md.
Relevant context: From `PROJECT_NOTES.md` §1 & §5: "AI-powered exam/answer-sheet correction platform for teachers ... Storage: Local filesystem only for now — `./uploads/` for images, `./results/{id}_grade.json` for output." From `notion.design.md`: `button-secondary: backgroundColor: 'transparent', textColor: '{colors.ink}', typography: '{typography.button-md}', rounded: '{rounded.md}', padding: '10px 18px', border: '1px solid {colors.hairline-strong}'`. Allows teachers to download a spreadsheet of student grades directly for university mark recording without external database dependencies.

**Status: COMPLETE** ✅ — Verified in PROGRESS.md. `GET /results/export.csv` streams valid CSV with all 12 results, and `.btn-secondary` export button is integrated in `templates/index.html`.

---

## Task 11: Create unified launcher script with pre-flight environment checks
Depends on: Task 10
Definition of done: Create a `start.py` launcher script that performs pre-flight verification:
1. Checks that Ollama is reachable at `http://127.0.0.1:11434`.
2. Checks that `glm-ocr` and `llama3.2:3b` are installed in Ollama.
3. Verifies that `./uploads` and `./results` directories exist (creates them if not).
4. Launches the FastAPI app via `uvicorn` on `0.0.0.0:8000` with Loguru logging, printing clear local access (`http://localhost:8000/`) and network instructions.
5. Supports a `--check-only` flag for non-blocking health validation.
Test running `python start.py --check-only` exiting with code 0 and all checks passing, and verify `GET http://127.0.0.1:8000/health` returns `{"status":"ok"}`. Record the output in PROGRESS.md.
Relevant context: From `PROJECT_NOTES.md` §1: "Deployment targets: Your personal consumer laptop (dev/testing) ... A college server later ... if it runs well on your consumer hardware, it will run on the college's hardware too." From `PROJECT_NOTES.md` §5: Use Loguru for clean, color-coded terminal startup messages. Avoid hardcoding assumptions so the single command `python start.py` allows the user/teacher to run the entire Inscrona MVP reliably.

**Status: COMPLETE** ✅ — Verified in PROGRESS.md. `start.py` implemented with pre-flight checks (Ollama reachable, models present, dirs ready). `--check-only` passed with code 0, background startup verified on `0.0.0.0:8000`, and `GET /health` and `GET /` responded HTTP 200.

---

## Task 12: Final end-to-end operational verification and user documentation
Depends on: Task 11
Definition of done: Create `README.md` containing concise operator instructions:
1. Prerequisites (Ollama running, models `glm-ocr` and `llama3.2:3b`).
2. Single-command launch (`python start.py`).
3. Accessing the Notion-designed UI at `http://localhost:8000/`.
4. Remote phone-access command via Pinggy (`ssh -p 443 -R0:localhost:8000 free.pinggy.io`).
5. Key features summary (image upload, HEIC/JPEG auto-conversion, ≤2000px resizing, sequential model execution, collapsible OCR drawer, confidence badge pills, past submissions table, CSV export).
Verify all documented commands are functional and record verification in PROGRESS.md.
Relevant context: From `PROJECT_NOTES.md` §11: "What 'done' looks like for the weekend MVP specifically: A single FastAPI service that serves an HTML upload form reachable via Pinggy tunnel from any phone/laptop browser, accepts an image (HEIC/JPEG, ≤2000px), sends to GLM-OCR sequentially, evaluates with Llama 3.2:3B to structured JSON, and saves results to local files." Ensure instructions are foolproof for the user to run their weekend MVP immediately.

**Status: COMPLETE** ✅ — Verified in PROGRESS.md. `README.md` documents prerequisites, `python start.py` launch, UI access, Pinggy remote access, and key features. `GET /health` and `GET /` verified HTTP 200.
