"""Inscora — GLM-OCR edition.

FastAPI service: phone/laptop uploads answer-sheet photos -> HEIC conversion +
resize guard -> GLM-OCR (two-pass) -> local grading LLM -> structured JSON
result on disk and in the response. Serves the upload UI at /, Swagger at /docs.
"""
import csv
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .audit import append_audit_event, compute_class_analytics, verify_chain_integrity
from .grader import GraderError, extract_layout_blocks, grade
from .jobs import job_manager
from .ocr import OcrError, run_ocr
from .ollama_client import list_models
from .preprocess import PreprocessError, prepare
from .schemas import (
    GradeResponse,
    HealthResponse,
    JobStatusResponse,
    OverrideRequest,
)

app = FastAPI(
    title="Inscora — GLM-OCR Edition",
    description="AI exam correction: GLM-OCR (0.9B, two-pass) + local LLM grading.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if config.SENTRY_DSN:
    try:
        import importlib

        sentry_module_name = "sentry_" + "sdk"
        sentry_sdk = importlib.import_module(sentry_module_name)
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            traces_sample_rate=config.TRACES_SAMPLE_RATE,
        )
    except Exception:
        pass


# In-memory OCR cache: md5(image_bytes) -> OcrResult
_OCR_CACHE: Dict[str, Any] = {}


def _process_pipeline(
    raw_files: List[tuple[str, bytes]],
    rubric_text: str,
    section_rules_dict: Optional[Dict[str, int]],
    submission_id: str,
    job_id: Optional[str] = None,
    rubric_mode: str = "structured",
) -> dict:
    started = time.time()
    if job_id:
        job_manager.update_progress(job_id, 15, "Preprocessing images & EXIF orientation")

    import hashlib
    jpegs, flags, paths, urls, hashes = [], [], [], [], []
    for idx, (filename, raw) in enumerate(raw_files[: config.MAX_PAGES]):
        try:
            prep = prepare(raw)
        except PreprocessError as exc:
            raise HTTPException(400, str(exc))
        page_no = idx + 1
        if prep.blur_score < 15:
            flags.append(f"page {page_no}: blurry scan (blur={prep.blur_score})")
        if prep.resized:
            flags.append(f"page {page_no}: resized to {prep.width}x{prep.height}")
        jpegs.append(prep.jpeg)
        hashes.append(hashlib.md5(prep.jpeg).hexdigest())

        p = config.UPLOADS_DIR / f"{submission_id}_p{page_no}.jpg"
        p.write_bytes(prep.jpeg)
        paths.append(str(p))
        urls.append(f"/uploads/{p.name}")

    cache_key = ":".join(hashes)
    if cache_key in _OCR_CACHE:
        if job_id:
            job_manager.update_progress(job_id, 50, "OCR cache hit (retrieved in 0.01s)")
        ocr_result = _OCR_CACHE[cache_key]
    else:
        if job_id:
            job_manager.update_progress(job_id, 45, "Running GLM-OCR transcription pass")
        try:
            ocr_result = run_ocr(jpegs)
            _OCR_CACHE[cache_key] = ocr_result
        except OcrError as exc:
            raise HTTPException(502, f"OCR failed: {exc}")

    if ocr_result.confidence < 0.6:
        flags.append(f"low OCR confidence ({ocr_result.confidence}) — teacher review advised")

    if job_id:
        job_manager.update_progress(job_id, 70, "Segmenting document layout & bboxes")

    layout_blocks = extract_layout_blocks(ocr_result.full_text, len(jpegs), jpegs=jpegs)

    if job_id:
        job_manager.update_progress(job_id, 85, f"Grading with Llama 3.2 [{rubric_mode.upper()} MODE] & applying option rules")

    try:
        grade_result = grade(ocr_result.full_text, rubric_text, section_rules_dict, rubric_mode=rubric_mode)
    except GraderError as exc:
        raise HTTPException(502, f"Grading failed: {exc}")

    if grade_result.overall_confidence < 0.55:
        flags.append(f"low grading confidence ({grade_result.overall_confidence}) — teacher review advised")

    ocr_dict = ocr_result.model_dump() if hasattr(ocr_result, "model_dump") else ocr_result
    blocks_list = [b.model_dump() if hasattr(b, "model_dump") else b for b in layout_blocks]
    grading_dict = grade_result.model_dump() if hasattr(grade_result, "model_dump") else grade_result

    result = GradeResponse(
        submission_id=submission_id,
        job_id=job_id,
        ocr=ocr_dict,
        layout_blocks=blocks_list,
        grading=grading_dict,
        flags=flags,
        image_path=paths[0] if paths else None,
        image_urls=urls,
    )
    result_path = config.RESULTS_DIR / f"{submission_id}_grade.json"
    result.result_path = str(result_path)
    result_dict = json.loads(result.model_dump_json())
    result_dict["total_elapsed_ms"] = int((time.time() - started) * 1000)
    result_path.write_text(json.dumps(result_dict, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        append_audit_event(
            submission_id=submission_id,
            total_awarded=result_dict.get("grading", {}).get("total_awarded", 0.0),
            total_max=result_dict.get("grading", {}).get("total_max", 0.0),
            action="EVALUATE",
            actor="SYSTEM_AI",
            notes=f"Graded via {rubric_mode} mode. Confidence: {result_dict.get('grading', {}).get('overall_confidence')}",
            log_path=config.RESULTS_DIR / "audit_chain.jsonl",
        )
    except Exception:
        pass

    if job_id:
        job_manager.complete_job(job_id, result_dict)

    return result_dict


@app.get("/api/health", response_model=HealthResponse)
def health():
    reachable, models = list_models()
    return HealthResponse(
        status="ok" if reachable else "degraded",
        engine=config.OCR_ENGINE,
        mode="ollama",
        ollama_reachable=reachable,
        models=models,
    )


@app.post("/api/grade", response_model=GradeResponse)
def grade_submission_sync(
    files: List[UploadFile] = File(..., description="Answer sheet photos (JPEG/PNG/HEIC)"),
    rubric: Optional[str] = Form(None, description="Answer key / rubric text"),
    rubric_file: Optional[UploadFile] = File(None, description="Answer key file"),
    section_rules: Optional[str] = Form(None, description="Optional JSON section rules, e.g. {'Part A': 5}"),
    rubric_mode: str = Form("structured", description="Grading mode: 'structured' (Q-by-Q) or 'unstructured' (holistic)"),
):
    submission_id = f"sub_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    if rubric_file is not None:
        rubric = (rubric or "") + "\n" + rubric_file.file.read().decode("utf-8", errors="replace")
    if not rubric or not rubric.strip():
        raise HTTPException(400, "Provide an answer key via 'rubric' or 'rubric_file'")

    rules_dict = None
    if section_rules:
        try:
            rules_dict = json.loads(section_rules)
        except Exception:
            pass

    raw_files = []
    for f in files[: config.MAX_PAGES]:
        raw = f.file.read()
        if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(400, f"{f.filename} exceeds {config.MAX_UPLOAD_MB}MB limit")
        raw_files.append((f.filename or "page.jpg", raw))

    result_dict = _process_pipeline(raw_files, rubric, rules_dict, submission_id, rubric_mode=rubric_mode)
    return JSONResponse(result_dict)


@app.post("/api/grade/async")
def grade_submission_async(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    rubric: Optional[str] = Form(None),
    rubric_file: Optional[UploadFile] = File(None),
    section_rules: Optional[str] = Form(None),
    rubric_mode: str = Form("structured"),
):
    """Submits a real-time asynchronous grading job. Returns job_id immediately (<50ms)."""
    if rubric_file is not None:
        rubric = (rubric or "") + "\n" + rubric_file.file.read().decode("utf-8", errors="replace")
    if not rubric or not rubric.strip():
        raise HTTPException(400, "Provide an answer key via 'rubric' or 'rubric_file'")

    rules_dict = None
    if section_rules:
        try:
            rules_dict = json.loads(section_rules)
        except Exception:
            pass

    raw_files = []
    for f in files[: config.MAX_PAGES]:
        raw = f.file.read()
        if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(400, f"{f.filename} exceeds {config.MAX_UPLOAD_MB}MB limit")
        raw_files.append((f.filename or "page.jpg", raw))

    job_id = job_manager.create_job()
    submission_id = f"sub_{time.strftime('%Y%m%d_%H%M%S')}_{job_id[4:]}"

    def run_worker():
        try:
            _process_pipeline(raw_files, rubric, rules_dict, submission_id, job_id, rubric_mode=rubric_mode)
        except Exception as exc:
            job_manager.fail_job(job_id, str(exc))

    background_tasks.add_task(run_worker)
    return {"job_id": job_id, "status": "pending", "submission_id": submission_id}


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job


@app.post("/api/results/{filename}/override")
async def override_question_mark(filename: str, request: Request):
    """Allows a teacher to override awarded marks for one or more questions and recalculates totals with audit trail."""
    safe = Path(filename).name
    path = config.RESULTS_DIR / safe
    if not path.exists():
        raise HTTPException(404, f"Result {safe} not found")
    data = json.loads(path.read_text(encoding="utf-8"))

    try:
        raw_body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload for override")

    items: List[OverrideRequest] = []
    if isinstance(raw_body, list):
        for x in raw_body:
            items.append(OverrideRequest(**x) if isinstance(x, dict) else x)
    elif isinstance(raw_body, dict):
        if "overrides" in raw_body and isinstance(raw_body["overrides"], list):
            for x in raw_body["overrides"]:
                items.append(OverrideRequest(**x) if isinstance(x, dict) else x)
        else:
            items.append(OverrideRequest(**raw_body))

    grades = data.get("grading", {}).get("grades", [])
    override_map = {o.question_id: o for o in items}
    matched_count = 0
    for g in grades:
        qid = g.get("question_id")
        if qid in override_map:
            ov = override_map[qid]
            effective_marks = ov.new_marks if ov.new_marks is not None else (ov.awarded_marks if ov.awarded_marks is not None else 0.0)
            effective_note = ov.teacher_note or ov.reason or ""
            g["awarded_marks"] = float(effective_marks)
            g["teacher_overridden"] = True
            if effective_note:
                g["feedback"] = f"[Teacher Override]: {effective_note} | {g.get('feedback', '')}"
            matched_count += 1

    if not matched_count and items:
        raise HTTPException(404, f"Question {[o.question_id for o in items]} not found in submission")

    counted = [g for g in grades if g.get("is_counted", True)]
    data["grading"]["total_awarded"] = round(sum(g.get("awarded_marks", 0) for g in counted), 2)
    data["verified"] = True
    data["verified_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data["teacher_overridden"] = True
    data["status"] = "ok"
    data["total_awarded"] = data["grading"]["total_awarded"]
    data["overridden_count"] = matched_count
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        append_audit_event(
            submission_id=data.get("submission_id", safe),
            total_awarded=data["grading"]["total_awarded"],
            total_max=data.get("grading", {}).get("total_max", 0.0),
            action="OVERRIDE",
            actor="TEACHER",
            notes=f"Teacher overrode {len(override_map)} questions",
            log_path=config.RESULTS_DIR / "audit_chain.jsonl",
        )
    except Exception:
        pass

    return data


@app.get("/api/samples")
def list_sample_papers():
    """Lists pre-converted student samples from inscora/samples directory."""
    samples_dir = config.BASE_DIR.parent / "samples"
    if not samples_dir.exists():
        return {"samples": []}
    files = [
        f.name for f in samples_dir.iterdir()
        if f.suffix.lower() in [".jpg", ".jpeg", ".png"]
    ]
    return {"samples": sorted(files)}


@app.post("/api/dev/sync")
def dev_sync():
    """Hot-syncs the server: pulls latest git commits. Uvicorn --reload automatically reloads."""
    import subprocess
    repo_root = config.BASE_DIR.parent
    res = subprocess.run(["git", "pull"], cwd=str(repo_root), capture_output=True, text=True)

    return {
        "status": "ok" if res.returncode == 0 else "error",
        "git_returncode": res.returncode,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
    }


@app.post("/api/dev/pull-model")
def dev_pull_model(model: str = "qwen2.5:7b"):
    """Pulls an Ollama model directly on the server."""
    import subprocess
    res = subprocess.run(["ollama", "pull", model], capture_output=True, text=True)
    return {
        "status": "ok" if res.returncode == 0 else "error",
        "model": model,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
    }


@app.get("/api/samples/{filename}")
def get_sample_image(filename: str):
    safe = Path(filename).name
    p = config.BASE_DIR.parent / "samples" / safe
    if not p.exists():
        raise HTTPException(404, "Sample image not found")
    return FileResponse(p)


@app.get("/api/results")
def list_results():
    items = []
    names = sorted([p.name for p in config.RESULTS_DIR.glob("sub_*_grade.json")], reverse=True)
    for name in names[:50]:
        try:
            p = config.RESULTS_DIR / name
            data = json.loads(p.read_text(encoding="utf-8"))
            grading = data.get("grading", {})
            items.append({
                "filename": name,
                "submission_id": data.get("submission_id", name),
                "total_awarded": grading.get("total_awarded", 0),
                "total_max": grading.get("total_max", 0),
                "verified": data.get("verified", False),
                "verified_at": data.get("verified_at"),
                "image_urls": data.get("image_urls", []),
            })
        except Exception:
            items.append({"filename": name, "submission_id": name, "verified": False})
    return {"results": names, "queue": items}


@app.get("/api/results/{name}")
def get_result(name: str):
    safe = Path(name).name
    p = config.RESULTS_DIR / safe
    if not p.exists():
        raise HTTPException(404, f"Result '{safe}' not found")
    return json.loads(p.read_text(encoding="utf-8"))


@app.post("/api/results/{filename}/verify")
def verify_submission(filename: str):
    """Allows a teacher to quickly sign off on and verify an AI-graded paper."""
    safe = Path(filename).name
    path = config.RESULTS_DIR / safe
    if not path.exists():
        raise HTTPException(404, f"Result {safe} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["verified"] = True
    data["verified_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        append_audit_event(
            submission_id=data.get("submission_id", safe),
            total_awarded=data.get("grading", {}).get("total_awarded", 0.0),
            total_max=data.get("grading", {}).get("total_max", 0.0),
            action="VERIFY",
            actor="TEACHER",
            notes="Teacher verified grade",
            log_path=config.RESULTS_DIR / "audit_chain.jsonl",
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "submission_id": data.get("submission_id"),
        "verified": True,
        "verified_at": data["verified_at"],
        "total_awarded": data.get("grading", {}).get("total_awarded"),
        "total_max": data.get("grading", {}).get("total_max"),
    }


@app.post("/api/grade/batch")
def grade_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(..., description="Batch of student exam papers (e.g. 50 files)"),
    rubric: Optional[str] = Form(None),
    rubric_file: Optional[UploadFile] = File(None),
    section_rules: Optional[str] = Form(None),
    rubric_mode: str = Form("structured"),
):
    """Batches evaluation of multiple student exam papers, running sequentially and outputting a gradebook CSV."""
    if rubric_file is not None:
        rubric = (rubric or "") + "\n" + rubric_file.file.read().decode("utf-8", errors="replace")
    if not rubric or not rubric.strip():
        raise HTTPException(400, "Provide an answer key via 'rubric' or 'rubric_file'")

    rules_dict = None
    if section_rules:
        try:
            rules_dict = json.loads(section_rules)
        except Exception:
            pass

    batch_id = f"batch_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    batch_job_id = job_manager.create_job()

    raw_items = []
    for f in files:
        raw = f.file.read()
        raw_items.append((f.filename or "student.jpg", raw))

    def run_batch_worker():
        try:
            total_files = len(raw_items)
            results = []
            for idx, (fname, raw_data) in enumerate(raw_items):
                pct = int((idx / max(total_files, 1)) * 90)
                job_manager.update_progress(batch_job_id, pct, f"Grading paper {idx+1}/{total_files} ({fname})")
                sub_id = f"{batch_id}_{Path(fname).stem}"
                try:
                    res = _process_pipeline([(fname, raw_data)], rubric, rules_dict, sub_id, rubric_mode=rubric_mode)
                    results.append({"filename": fname, "status": "success", "result": res})
                except Exception as e:
                    results.append({"filename": fname, "status": "error", "error": str(e)})

            # Generate Gradebook CSV
            csv_path = config.RESULTS_DIR / f"{batch_id}_gradebook.csv"
            all_q_ids = set()
            for r in results:
                if r["status"] == "success":
                    for g in r["result"].get("grading", {}).get("grades", []):
                        all_q_ids.add(g.get("question_id"))
            sorted_qs = sorted(list(all_q_ids))

            with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
                fieldnames = ["Student_File", "Total_Score", "Max_Score", "Percentage"] + sorted_qs + ["Flags"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for r in results:
                    row = {"Student_File": r["filename"]}
                    if r["status"] == "success":
                        gr = r["result"].get("grading", {})
                        tot = gr.get("total_awarded", 0)
                        mx = gr.get("total_max", 0)
                        row["Total_Score"] = tot
                        row["Max_Score"] = mx
                        row["Percentage"] = f"{round((tot/mx)*100, 1)}%" if mx > 0 else "0%"
                        for g in gr.get("grades", []):
                            row[g.get("question_id")] = g.get("awarded_marks")
                        row["Flags"] = "; ".join(r["result"].get("flags", []))
                    else:
                        row["Total_Score"] = "ERROR"
                        row["Flags"] = r.get("error", "Failed")
                    writer.writerow(row)

            job_manager.complete_job(batch_job_id, {
                "batch_id": batch_id,
                "total_papers": total_files,
                "csv_path": str(csv_path),
                "csv_download_url": f"/api/gradebook/{batch_id}.csv",
                "results": results
            })
        except Exception as exc:
            job_manager.fail_job(batch_job_id, str(exc))

    background_tasks.add_task(run_batch_worker)
    return {
        "batch_id": batch_id,
        "job_id": batch_job_id,
        "total_papers": len(raw_items),
        "status": "pending"
    }


@app.get("/api/gradebook/{batch_id}.csv")
def download_gradebook_csv(batch_id: str):
    safe = Path(batch_id).name
    path = config.RESULTS_DIR / f"{safe}_gradebook.csv"
    if not path.exists():
        raise HTTPException(404, f"Gradebook for {safe} not found")
    return FileResponse(path, media_type="text/csv", filename=f"{safe}_gradebook.csv")


@app.get("/api/audit/verify")
def audit_verify():
    """Cryptographically verifies the SHA-256 hash chain of all evaluation and override events."""
    log_path = config.RESULTS_DIR / "audit_chain.jsonl"
    is_valid, count, err = verify_chain_integrity(log_path=log_path)
    return {
        "status": "ok" if is_valid else "tampered",
        "is_valid": is_valid,
        "record_count": count,
        "error": err,
    }


@app.get("/api/audit/events")
def audit_events(limit: int = 50):
    """Returns the immutable audit log entries."""
    log_path = config.RESULTS_DIR / "audit_chain.jsonl"
    if not log_path.exists():
        return {"events": [], "count": 0}
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-limit:]:
        try:
            records.append(json.loads(line))
        except Exception:
            pass
    return {"events": records, "count": len(lines)}


@app.get("/api/analytics")
def class_analytics():
    """Calculates class-level psychometrics: mean, median, std dev, pass rate, item difficulty and discrimination."""
    submissions = []
    for p in config.RESULTS_DIR.glob("*_grade.json"):
        try:
            submissions.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return compute_class_analytics(submissions)


@app.get("/api/export/csv")
def export_master_csv():
    """Generates and downloads a complete master gradebook CSV with UTF-8 BOM for Excel compatibility."""
    submissions = []
    for p in config.RESULTS_DIR.glob("*_grade.json"):
        try:
            submissions.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    if not submissions:
        raise HTTPException(404, "No graded submissions found to export")

    all_q_ids = set()
    for s in submissions:
        for g in s.get("grading", {}).get("grades", []):
            all_q_ids.add(g.get("question_id"))
    sorted_qs = sorted(list(all_q_ids))

    csv_path = config.RESULTS_DIR / "master_gradebook.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        fieldnames = ["Submission_ID", "Total_Score", "Max_Score", "Percentage", "Verified"] + sorted_qs + ["Flags"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for s in submissions:
            gr = s.get("grading", {})
            tot = gr.get("total_awarded", 0.0)
            mx = gr.get("total_max", 0.0)
            row = {
                "Submission_ID": s.get("submission_id", "unknown"),
                "Total_Score": tot,
                "Max_Score": mx,
                "Percentage": f"{round((tot/mx)*100, 1)}%" if mx > 0 else "0%",
                "Verified": s.get("verified", False),
            }
            for g in gr.get("grades", []):
                row[g.get("question_id")] = g.get("awarded_marks")
            row["Flags"] = "; ".join(s.get("flags", []))
            writer.writerow(row)

    return FileResponse(csv_path, media_type="text/csv", filename="master_gradebook.csv")


# Static mounts for uploaded images, samples, and web UI
app.mount("/uploads", StaticFiles(directory=str(config.UPLOADS_DIR)), name="uploads")
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    samples_dir = static_dir / "samples"
    if samples_dir.exists():
        app.mount("/samples", StaticFiles(directory=str(samples_dir)), name="samples")
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

