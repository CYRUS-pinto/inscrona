"""
Inscora API routes — OCR, grading, answer keys, jobs, results.
"""

from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from .answer_key import (
    AnswerKey,
    AnswerKeyEntry,
    create_sample_answer_key,
    load_answer_key,
    load_answer_key_from_dict,
    validate_answer_key,
)
from .config import (
    ANSWER_KEY_PATH,
    MAX_UPLOAD_MB,
    OLLAMA_HOST,
    OCR_ENGINE,
    OCR_MODE,
    OCR_TIMEOUT_S,
    GRADE_MODEL,
    GRADE_TIMEOUT_S,
    MAX_PAGES,
    DATALAB_API_URL,
    DATALAB_API_KEY,
    KEEP_ALIVE,
)
from .feedback import generate_feedback
from .grader import grade_paper
from .jobs import JobManager, JobStatus
from .middleware import InscronaException, OcrError, GradingError, AnswerKeyError
from .ocr import ocr_page, OcrError as OcrEngineError
from .schemas import (
    GradeResult,
    JobCreateResponse,
    JobListResponse,
    JobStatusResponse,
    OcrResult,
    PageOcr,
    QuestionGrade,
    ReviewFlag,
    SectionSummary,
)

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "edition": "unified-inscora",
        "ocr_engine": OCR_ENGINE,
        "grade_model": GRADE_MODEL,
        "ollama_host": OLLAMA_HOST,
    }


# ---------------------------------------------------------------------------
# Answer Key
# ---------------------------------------------------------------------------

@router.post("/answer-key")
def create_answer_key(payload: dict):
    """Create or update answer key from JSON payload."""
    try:
        answer_key = load_answer_key_from_dict(payload)
        errors = validate_answer_key(answer_key)
        if errors:
            raise AnswerKeyError(f"Answer key validation failed: {errors}")
        # Save to disk
        import json
        ANSWER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        ANSWER_KEY_PATH.write_text(json.dumps(answer_key.to_dict(), indent=2), encoding="utf-8")
        return {"status": "created", "questions": len(answer_key.entries)}
    except AnswerKeyError:
        raise
    except Exception as e:
        raise AnswerKeyError(f"Failed to create answer key: {e}")


@router.get("/answer-key")
def get_answer_key():
    """Get the current answer key."""
    try:
        answer_key = load_answer_key()
        return answer_key.to_dict()
    except FileNotFoundError:
        return {"message": "No answer key found", "questions": {}}
    except Exception as e:
        raise AnswerKeyError(f"Failed to load answer key: {e}")


@router.put("/answer-key")
def update_answer_key(payload: dict):
    """Update the entire answer key."""
    try:
        answer_key = load_answer_key_from_dict(payload)
        errors = validate_answer_key(answer_key)
        if errors:
            raise AnswerKeyError(f"Answer key validation failed: {errors}")
        import json
        ANSWER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        ANSWER_KEY_PATH.write_text(json.dumps(answer_key.to_dict(), indent=2), encoding="utf-8")
        return {"status": "updated", "questions": len(answer_key.entries)}
    except AnswerKeyError:
        raise
    except Exception as e:
        raise AnswerKeyError(f"Failed to update answer key: {e}")


@router.delete("/answer-key")
def delete_answer_key():
    """Delete the answer key."""
    try:
        if ANSWER_KEY_PATH.exists():
            ANSWER_KEY_PATH.unlink()
            return {"status": "deleted"}
        return {"message": "No answer key to delete"}
    except Exception as e:
        raise AnswerKeyError(f"Failed to delete answer key: {e}")


@router.post("/answer-key/sample")
def load_sample_answer_key():
    """Load a sample answer key for testing."""
    try:
        answer_key = create_sample_answer_key()
        import json
        ANSWER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        ANSWER_KEY_PATH.write_text(json.dumps(answer_key.to_dict(), indent=2), encoding="utf-8")
        return {"status": "loaded", "questions": len(answer_key.entries)}
    except Exception as e:
        raise AnswerKeyError(f"Failed to load sample answer key: {e}")


# ---------------------------------------------------------------------------
# OCR — answer key pages
# ---------------------------------------------------------------------------

@router.post("/ocr/answer-key")
async def ocr_answer_key_pages(
    files: list[UploadFile] = File(..., description="Answer key page images/PDFs"),
):
    """OCR pages uploaded as answer key — returns extracted text per page."""
    if not files:
        raise OcrError("No files uploaded")
    if len(files) > MAX_PAGES:
        raise OcrError(f"Too many pages: {len(files)} > {MAX_PAGES}")

    results = []
    for i, upload in enumerate(files):
        content = await upload.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            raise OcrError(f"File {upload.filename} too large: {size_mb:.1f}MB > {MAX_UPLOAD_MB}MB")
        try:
            result = await ocr_page(content, page_num=i + 1)
            results.append(result)
        except OcrEngineError as e:
            raise OcrError(f"OCR failed on page {i + 1}: {e}")

    return {"pages": [r.model_dump() for r in results], "total": len(results)}


# ---------------------------------------------------------------------------
# OCR — student papers
# ---------------------------------------------------------------------------

@router.post("/ocr/papers")
async def ocr_student_papers(
    files: list[UploadFile] = File(..., description="Student paper images/PDFs"),
):
    """OCR student answer papers — returns extracted text per page."""
    if not files:
        raise OcrError("No files uploaded")
    if len(files) > MAX_PAGES:
        raise OcrError(f"Too many pages: {len(files)} > {MAX_PAGES}")

    results = []
    for i, upload in enumerate(files):
        content = await upload.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            raise OcrError(f"File {upload.filename} too large: {size_mb:.1f}MB > {MAX_UPLOAD_MB}MB")
        try:
            result = await ocr_page(content, page_num=i + 1)
            results.append(result)
        except OcrEngineError as e:
            raise OcrError(f"OCR failed on page {i + 1}: {e}")

    return {"pages": [r.model_dump() for r in results], "total": len(results)}


# ---------------------------------------------------------------------------
# Grading — async (background job)
# ---------------------------------------------------------------------------

@router.post("/grade")
async def start_grading(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(..., description="Student paper images/PDFs"),
    student_name: str = Query(default="Unknown Student"),
    student_id: str = Query(default=""),
    section_rule: str = Query(
        default=None,
        description="Section rule: 'best5of7', 'all', or null (use all questions)",
    ),
):
    """Start async grading — returns job_id for polling."""
    if not files:
        raise OcrError("No files uploaded")
    if len(files) > MAX_PAGES:
        raise OcrError(f"Too many pages: {len(files)} > {MAX_PAGES}")

    # Validate files
    for upload in files:
        content = await upload.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            raise OcrError(f"File {upload.filename} too large: {size_mb:.1f}MB > {MAX_UPLOAD_MB}MB")
        upload.file.seek(0)

    # Create job
    job = JobManager.create_job(
        total_pages=len(files),
        student_name=student_name,
        student_id=student_id,
    )

    # Load answer key
    try:
        answer_key = load_answer_key()
    except FileNotFoundError:
        job.fail("No answer key found. Create one via /api/answer-key first.")
        raise AnswerKeyError("No answer key found. Create one via /api/answer-key first.")

    # Process files into byte list
    all_contents = []
    for upload in files:
        all_contents.append(await upload.read())

    # Submit background task
    background_tasks.add_task(
        _process_grading,
        job_id=job.id,
        all_contents=all_contents,
        student_name=student_name,
        student_id=student_id,
        answer_key=answer_key,
        section_rule=section_rule,
    )

    return JobCreateResponse(
        job_id=job.id,
        status=job.status.value,
        message="Grading started",
    )


async def _process_grading(
    job_id: str,
    all_contents: list[bytes],
    student_name: str,
    student_id: str,
    answer_key: AnswerKey,
    section_rule: str | None,
):
    """Background grading task — OCR pages then grade."""
    import traceback
    from .jobs import JobManager

    job = JobManager.get_job(job_id)
    if not job:
        return

    try:
        job.update_progress(current_step="ocr", pages_done=0, total_pages=len(all_contents))

        # Phase 1: OCR all pages
        ocr_results: list[OcrResult] = []
        for i, content in enumerate(all_contents):
            try:
                result = await ocr_page(content, page_num=i + 1)
                ocr_results.append(result)
                job.update_progress(current_step="ocr", pages_done=i + 1, total_pages=len(all_contents))
            except OcrEngineError as e:
                # Record page error but continue
                ocr_results.append(OcrResult(
                    raw_text=f"[OCR ERROR: {e}]",
                    confidence=0.0,
                    page_num=i + 1,
                    method="error",
                ))

        # Phase 2: Grade
        job.update_progress(current_step="grading", pages_done=0, total_pages=len(all_contents))

        answer_key_dict = answer_key.to_dict()
        try:
            grade_result = await grade_paper(
                ocr_results=ocr_results,
                answer_key=answer_key_dict,
                student_name=student_name,
                student_id=student_id,
                section_rule=section_rule,
            )
        except Exception as e:
            job.fail(f"Grading failed: {e}")
            return

        # Generate feedback
        feedback = generate_feedback(grade_result, answer_key_dict, student_name)

        # Store result in job
        job.complete(grade_result=grade_result, feedback=feedback)

    except Exception as e:
        tb = traceback.format_exc()
        job.fail(f"Unexpected error: {e}\n{tb}")


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------

@router.get("/jobs")
def list_jobs():
    """List all jobs."""
    jobs = JobManager.list_jobs()
    return JobListResponse(jobs=[j.to_dict() for j in jobs])


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    """Get status of a specific job."""
    job = JobManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobStatusResponse(**job.to_dict())


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str):
    """Cancel a running job."""
    job = JobManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    job.cancel()
    return {"status": "cancelled", "job_id": job_id}


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@router.get("/results/{job_id}")
def get_results(job_id: str):
    """Get grading results for a completed job."""
    job = JobManager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job {job_id} is {job.status.value}, not completed",
        )
    return {
        "job_id": job_id,
        "grade_result": job.grade_result.model_dump() if job.grade_result else None,
        "feedback": job.feedback,
    }


# ---------------------------------------------------------------------------
# Sync grading (single request, no job)
# ---------------------------------------------------------------------------

@router.post("/grade/sync")
async def grade_sync(
    files: list[UploadFile] = File(..., description="Student paper images/PDFs"),
    student_name: str = Query(default="Unknown Student"),
    student_id: str = Query(default=""),
    section_rule: str = Query(default=None),
):
    """Synchronous grading — waits for full result before responding."""
    if not files:
        raise OcrError("No files uploaded")
    if len(files) > MAX_PAGES:
        raise OcrError(f"Too many pages: {len(files)} > {MAX_PAGES}")

    # Load answer key
    try:
        answer_key = load_answer_key()
    except FileNotFoundError:
        raise AnswerKeyError("No answer key found. Create one via /api/answer-key first.")

    # OCR all pages
    ocr_results: list[OcrResult] = []
    for i, upload in enumerate(files):
        content = await upload.read()
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            raise OcrError(f"File {upload.filename} too large: {size_mb:.1f}MB > {MAX_UPLOAD_MB}MB")
        try:
            result = await ocr_page(content, page_num=i + 1)
            ocr_results.append(result)
        except OcrEngineError as e:
            raise OcrError(f"OCR failed on page {i + 1}: {e}")

    # Grade
    answer_key_dict = answer_key.to_dict()
    grade_result = await grade_paper(
        ocr_results=ocr_results,
        answer_key=answer_key_dict,
        student_name=student_name,
        student_id=student_id,
        section_rule=section_rule,
    )

    feedback = generate_feedback(grade_result, answer_key_dict, student_name)

    return {
        "grade_result": grade_result.model_dump(),
        "feedback": feedback,
    }


# ---------------------------------------------------------------------------
# Latest analysis / recent results
# ---------------------------------------------------------------------------

@router.get("/results")
def get_latest_analysis():
    """Get the most recent grading results across all jobs."""
    jobs = JobManager.list_jobs()
    completed = [j for j in jobs if j.status == JobStatus.COMPLETED and j.grade_result]
    if not completed:
        return {"message": "No completed jobs yet", "results": []}

    # Return last 10 completed jobs
    recent = sorted(completed, key=lambda j: j.updated_at or "", reverse=True)[:10]
    return {
        "results": [
            {
                "job_id": j.id,
                "student_name": j.student_name,
                "student_id": j.student_id,
                "total_score": j.grade_result.total_score if j.grade_result else None,
                "max_score": j.grade_result.max_score if j.grade_result else None,
                "completed_at": j.updated_at,
            }
            for j in recent
        ]
    }
