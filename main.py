"""Inscrona FastAPI backend — sequential OCR + grading pipeline."""
import base64
import csv
import io
import json
import os
import time
import uuid
import secrets
import hashlib
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Set, Optional, List, Any
from functools import lru_cache
from contextlib import asynccontextmanager

try:
    import pillow_heif
except ImportError:
    pillow_heif = None
import requests
import httpx
import sentry_sdk
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from pydantic.types import PositiveInt
from batch import StagedBatchManager
from cloud_api import cloud_grade, is_cloud_api_available
from blocks import extract_document_blocks


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (stdlib only — no new dependencies per CONSTRAINTS.md).

    Parses KEY=VALUE lines, ignores blanks and #-comments, strips matching
    quotes. Never overrides variables already present in the environment.
    """
    try:
        text = Path(path).read_text(encoding="utf-8").lstrip("\ufeff")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


_load_dotenv()

# ---------------------------------------------------------------------------
# Sentry initialization
# ---------------------------------------------------------------------------
SENTRY_DSN = "https://fb59bcf7c053c5dc895b6e61de94a571@o4511881652076544.ingest.de.sentry.io/4512032347717712"
sentry_sdk.init(
    dsn=SENTRY_DSN,
    send_default_pii=True,
    traces_sample_rate=0.1,
    profiles_sample_rate=0.1,
    environment=os.getenv("ENVIRONMENT", "development"),
)
logger.info("Sentry initialized")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OLLAMA_URL = "http://127.0.0.1:11434"
UPLOAD_DIR = Path("./uploads")
RESULT_DIR = Path("./results")
MAX_LONGEST_EDGE = 2000
# OCR tuning knobs (Phase 1 Task 3 — measured, see PROGRESS.md sweep table).
# Narrower edge / lower JPEG quality cut vision tokens (faster); the terse
# prompt cuts prompt tokens. Adopt a combo only via the eval-delta gate.
OCR_LONGEST_EDGE = 2000
OCR_JPEG_QUALITY = 90
OCR_PROMPT_TERSE = False
GRADE_NUM_PREDICT = 2048
LOCAL_GRADING_MODEL = os.getenv("LOCAL_GRADING_MODEL", "llama3.2:3b")
LOCAL_OCR_MODEL = os.getenv("LOCAL_OCR_MODEL", "glm-ocr")

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# Register HEIC opener with Pillow
if pillow_heif:
    pillow_heif.register_heif_opener()

from PIL import Image  # noqa: E402  (must come after heif registration)

# ---------------------------------------------------------------------------
# Pairing & Auth
# ---------------------------------------------------------------------------

PAIRING_TOKENS: Dict[str, dict] = {}  # token -> {url, expires, created}
ACTIVE_WS: Dict[str, Set[WebSocket]] = {}  # job_id -> {websockets}

security = HTTPBearer(auto_error=False)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authentication")
    token = credentials.credentials
    if token not in PAIRING_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if datetime.now() > PAIRING_TOKENS[token]["expires"]:
        del PAIRING_TOKENS[token]
        raise HTTPException(status_code=401, detail="Token expired")
    return token


async def ws_auth(websocket: WebSocket, token: str) -> str:
    if token not in PAIRING_TOKENS:
        await websocket.close(code=4001, reason="Invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")
    if datetime.now() > PAIRING_TOKENS[token]["expires"]:
        await websocket.close(code=4001, reason="Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    return token

# ---------------------------------------------------------------------------
# Pydantic schemas with validation
# ---------------------------------------------------------------------------

class RubricCriteria(BaseModel):
    """Individual grading criterion."""
    name: str = Field(..., min_length=1, max_length=100)
    weight: float = Field(..., ge=0.0, le=1.0)
    description: str = Field(default="", max_length=500)
    max_marks: PositiveInt = Field(default=10)

class GradingRubric(BaseModel):
    """Structured grading rubric."""
    criteria: List[RubricCriteria] = Field(default_factory=list)
    overall_instruction: str = Field(
        default="Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity.",
        max_length=2000
    )
    pass_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    
    @field_validator('criteria')
    @classmethod
    def validate_weights(cls, v):
        if v:
            total = sum(c.weight for c in v)
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Criteria weights must sum to 1.0, got {total}")
        return v

class QuestionGrade(BaseModel):
    """Grade for a single question."""
    question_id: str = Field(..., min_length=1)
    question_text: str = Field(default="", max_length=2000)
    marks_awarded: float = Field(..., ge=0)
    max_marks: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    feedback: str = Field(default="", max_length=1000)
    criterion_scores: Dict[str, float] = Field(default_factory=dict)

class GradeResult(BaseModel):
    """Complete grading result."""
    job_id: str = Field(..., min_length=1)
    total_marks: float = Field(..., ge=0)
    max_total_marks: float = Field(..., gt=0)
    percentage: float = Field(..., ge=0.0, le=100.0)
    overall_confidence: float = Field(..., ge=0.0, le=1.0)
    confidence_level: str = Field(..., pattern="^(high|medium|low)$")
    feedback: str = Field(default="", max_length=2000)
    question_grades: List[QuestionGrade] = Field(default_factory=list)
    ocr_text: str = Field(default="", max_length=50000)
    blocks: List[Dict[str, Any]] = Field(default_factory=list)
    processing_time_ms: int = Field(default=0, ge=0)
    model_used: str = Field(default="", max_length=50)
    fallback_used: bool = Field(default=False)
    flags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    @property
    def is_pass(self) -> bool:
        return self.percentage >= 40.0
    
    @property
    def letter_grade(self) -> str:
        p = self.percentage
        if p >= 90: return "A+"
        elif p >= 80: return "A"
        elif p >= 70: return "B+"
        elif p >= 60: return "B"
        elif p >= 50: return "C"
        elif p >= 40: return "D"
        else: return "F"

class GradeRequest(BaseModel):
    """Request model for grading."""
    rubric: str = Field(default="Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity.", max_length=2000)
    structured_rubric: Optional[GradingRubric] = None
    return_ocr: bool = Field(default=True)
    return_question_breakdown: bool = Field(default=False)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Inscrona", version="0.1.0")
batch_mgr = StagedBatchManager(db_path="database.db")



@app.get("/health")
def health():
    return {
        "status": "ok",
        "mode": _current_mode(),
        "colab_circuit_open": _colab_breaker["state"] == "OPEN",
        "cloud_api_available": is_cloud_api_available(),
    }


@app.get("/sentry-debug")
async def sentry_debug():
    """Trigger a test error to verify Sentry integration."""
    division_by_zero = 1 / 0
    return {"status": "this will never be reached"}


@app.get("/")
def index():
    return FileResponse(Path("templates/index.html"), media_type="text/html")


@app.get("/results")
def list_results():
    """Return a list of all graded jobs with summary info."""
    results = []
    for p in sorted(RESULT_DIR.glob("*_grade.json"), key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            job_id = p.stem.replace("_grade", "")
            results.append({
                "job_id": job_id,
                "marks": data.get("total_marks", data.get("marks", 0)),
                "confidence": data.get("overall_confidence", data.get("confidence", 0)),
                "total_marks": data.get("total_marks", data.get("marks", 0)),
                "max_total_marks": data.get("max_total_marks", 10),
                "percentage": data.get("percentage", 0),
                "overall_confidence": data.get("overall_confidence", data.get("confidence", 0)),
                "feedback": data.get("feedback", ""),
                "timestamp": p.stat().st_mtime,
            })
        except Exception:
            continue
    return {"results": results}


@app.get("/results/export.csv")
def export_csv():
    """Stream a CSV of all grading results."""
    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["job_id", "marks", "confidence", "feedback"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)

        for p in sorted(RESULT_DIR.glob("*_grade.json"), key=lambda f: f.stat().st_mtime):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                job_id = p.stem.replace("_grade", "")
                writer.writerow([
                    job_id,
                    data.get("total_marks", data.get("marks", "")),
                    data.get("overall_confidence", data.get("confidence", "")),
                    data.get("feedback", ""),
                ])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
            except Exception:
                continue

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=grades_export.csv"},
    )


@app.get("/results/{job_id}")
def get_result(job_id: str):
    """Return the full grading result for a specific job."""
    result_path = RESULT_DIR / f"{job_id}_grade.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail=f"Result {job_id} not found")
    data = json.loads(result_path.read_text(encoding="utf-8"))
    data["job_id"] = job_id
    data["timestamp"] = result_path.stat().st_mtime
    if "blocks" not in data or not data["blocks"]:
        data["blocks"] = extract_document_blocks(
            data.get("ocr_text", ""),
            data.get("question_grades", [])
        )
    return data


# ---------------------------------------------------------------------------
# Improved OCR and Grading Prompts
# ---------------------------------------------------------------------------

OCR_PROMPT = """You are an expert OCR system for educational answer sheets. Extract ALL text from this handwritten answer sheet image with maximum accuracy.

Guidelines:
1. Preserve the exact structure: question numbers, parts (a, b, c), sub-parts
2. Include ALL text: questions, answers, diagrams descriptions, crossed-out text (mark as [crossed out: ...])
3. Preserve mathematical notation, formulas, and symbols exactly
4. Keep paragraph breaks and line structure
5. Note any diagrams, tables, or graphs: [DIAGRAM: description] or [TABLE: data]
6. For illegible text, mark as [ILLEGIBLE] - do not guess
7. Preserve original spelling/grammar errors - do not correct
8. Include page numbers, question numbers, student details if visible

Output format: Plain text preserving all layout and structure."""

OCR_PROMPT_TERSE_TEXT = """Transcribe all visible text, preserve question numbers and layout."""


def _ocr_prompt() -> str:
    """Full guidelines prompt unless the terse sweep knob is on."""
    return OCR_PROMPT_TERSE_TEXT if OCR_PROMPT_TERSE else OCR_PROMPT

GRADING_PROMPT_TEMPLATE = """You are an expert academic grader evaluating student answers. Be fair, consistent, and thorough.

STUDENT ANSWER:
{ocr_text}

RUBRIC / INSTRUCTIONS:
{rubric}

GRADING REQUIREMENTS:
1. Analyze EACH question/part separately
2. Award marks based on: correctness, completeness, clarity, depth
3. For partial credit: explain what's correct vs missing/incorrect
4. Consider: key concepts, terminology, reasoning, examples, diagrams
5. Be specific in feedback - reference exact parts of student's answer
6. Confidence: How certain are you (0.0-1.0) based on OCR clarity and answer quality

OUTPUT ONLY VALID JSON in this exact format:
{{
    "total_marks": <float>,
    "max_total_marks": <float>,
    "percentage": <float>,
    "overall_confidence": <0.0-1.0>,
    "confidence_level": "<high|medium|low>",
    "feedback": "<detailed overall assessment>",
    "question_grades": [
        {{
            "question_id": "Q1",
            "question_text": "<brief question summary>",
            "marks_awarded": <float>,
            "max_marks": <float>,
            "confidence": <0.0-1.0>,
            "feedback": "<specific feedback for this question>",
            "criterion_scores": {{}}
        }}
    ],
    "flags": ["<any issues: ocr_uncertain, incomplete_answer, diagram_missing, etc>"],
    "model_used": "llama3.2:3b",
    "fallback_used": false
}}"""

# ---------------------------------------------------------------------------
# Core Grading Endpoint
# ---------------------------------------------------------------------------

@app.post("/grade", response_model=GradeResult)
async def grade(
    file: UploadFile = File(...),
    rubric: str = Form(default="Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity."),
    structured_rubric: Optional[str] = Form(default=None),
    return_ocr: bool = Form(default=True),
    return_question_breakdown: bool = Form(default=True),
    burst: bool = False,
    warm: bool = False,
):
    """Grade a student answer sheet image."""
    job_id = uuid.uuid4().hex[:12]
    start_time = time.perf_counter()
    fallback_used = False
    
    logger.info(f"[{job_id}] Received grading request -- file={file.filename}")

    # -- 1. Save uploaded image --
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    ext = Path(file.filename or "upload.jpg").suffix.lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp'}:
        raise HTTPException(status_code=400, detail=f"Unsupported file format: {ext}")
    
    saved_path = UPLOAD_DIR / f"{job_id}{ext}"
    saved_path.write_bytes(raw_bytes)
    logger.info(f"[{job_id}] Saved upload to {saved_path} ({len(raw_bytes)} bytes)")

    # -- 2. Convert HEIC to JPEG and resize --
    try:
        img = Image.open(saved_path)
        img.verify()  # Verify it's a valid image
        img = Image.open(saved_path)  # Reopen after verify
        
        if ext in (".heic", ".heif"):
            jpeg_path = UPLOAD_DIR / f"{job_id}.jpg"
            img.save(jpeg_path, "JPEG", quality=90, optimize=True)
            saved_path.unlink()
            saved_path = jpeg_path
            logger.info(f"[{job_id}] Converted HEIC to JPEG: {saved_path}")
    except Exception as e:
        logger.error(f"[{job_id}] Failed to open image: {e}")
        raise HTTPException(status_code=400, detail=f"Cannot open image: {e}")

    # Resize if too large (GLM-OCR crashes >2300px)
    w, h = img.size
    if max(w, h) > OCR_LONGEST_EDGE:
        scale = OCR_LONGEST_EDGE / max(w, h)
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
        img.save(saved_path, "JPEG", quality=OCR_JPEG_QUALITY, optimize=True)
        logger.info(f"[{job_id}] Resized {w}x{h} -> {new_size[0]}x{new_size[1]} (edge={OCR_LONGEST_EDGE}, q={OCR_JPEG_QUALITY})")

    # -- 3. Convert to base64 --
    with open(saved_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    # -- 4. Run inference with fallback --
    try:
        result = await _grade_with_fallback(
            image_b64=image_b64,
            rubric=rubric,
            job_id=job_id,
            return_question_breakdown=return_question_breakdown,
            burst=burst,
            warm=warm,
        )
        fallback_used = result.get("fallback_used", False)
    except Exception as e:
        logger.error(f"[{job_id}] All inference failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # -- 5. Build final result with timing --
    processing_time_ms = int((time.perf_counter() - start_time) * 1000)
    
    # Parse structured rubric if provided
    structured_rubric_obj = None
    if structured_rubric:
        try:
            structured_rubric_obj = GradingRubric.model_validate_json(structured_rubric)
            # Merge with rubric text
            rubric = f"{rubric}\n\nStructured Criteria:\n" + "\n".join(
                f"- {c.name} (weight: {c.weight}): {c.description}" 
                for c in structured_rubric_obj.criteria
            )
        except Exception as e:
            logger.warning(f"[{job_id}] Invalid structured_rubric: {e}")

    # Build final result
    _total = float(result.get("total_marks", 0) or 0)
    _max = float(result.get("max_total_marks", 10) or 10)
    # Compute percentage server-side -- never trust the LLM's arithmetic
    _pct = round(100.0 * _total / _max, 1) if _max > 0 else 0.0
    result_data = {
        "job_id": job_id,
        "total_marks": _total,
        "max_total_marks": _max,
        "percentage": _pct,
        "overall_confidence": result.get("overall_confidence", 0.5),
        "confidence_level": result.get("confidence_level", "medium"),
        "feedback": result.get("feedback", ""),
        "question_grades": result.get("question_grades", []),
        "ocr_text": result.get("ocr_text", "") if return_ocr else "",
        "processing_time_ms": processing_time_ms,
        "model_used": result.get("model_used", "unknown"),
        "fallback_used": fallback_used,
        "flags": result.get("flags", []),
    }

    # Add flags for quality issues
    flags = result_data["flags"]
    if result.get("overall_confidence", 1.0) < 0.5:
        flags.append("low_confidence")
    if len(result.get("ocr_text", "")) < 50:
        flags.append("minimal_ocr_text")
    if not result.get("question_grades"):
        flags.append("no_question_breakdown")

    result_data["flags"] = flags

    # Validate and create result
    try:
        final_result = GradeResult(**result_data)
    except Exception as e:
        logger.error(f"[{job_id}] Result validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Result validation failed: {e}")

    # -- 6. Save result --
    result_path = RESULT_DIR / f"{job_id}_grade.json"
    result_dict = final_result.model_dump()
    result_path.write_text(json.dumps(result_dict, indent=2, default=str), encoding="utf-8")
    logger.info(f"[{job_id}] Saved grade to {result_path} (processed in {processing_time_ms}ms)")

    # Broadcast completion
    _broadcast_progress(job_id, {
        "stage": "completed",
        "progress": 100,
        "message": "Complete!",
        "result": result_dict,
    })

    return final_result



# ---------------------------------------------------------------------------
# Staged Batch & Decoupled Re-Grading Pipeline
# ---------------------------------------------------------------------------

async def _process_phase2_grading(batch_id: str, rubric: str):
    await batch_mgr.set_batch_phase(batch_id, 2, "phase2_grading")
    status = await batch_mgr.get_status(batch_id)
    papers = status["papers"]
    logger.info(f"[batch {batch_id}] Phase 2: Bulk evaluation starting for {len(papers)} papers")
    
    for p in papers:
        jid = p["job_id"]
        ocr_text = p.get("ocr_text", "")
        if not ocr_text:
            continue
        try:
            grade_prompt = GRADING_PROMPT_TEMPLATE.format(ocr_text=ocr_text, rubric=rubric)
            grade_raw = await asyncio.to_thread(
                _ollama_generate, LOCAL_GRADING_MODEL, grade_prompt,
                keep_alive=300, format_json=True, num_ctx=4096,
                num_predict=GRADE_NUM_PREDICT
            )
            cleaned = grade_raw.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join([l for l in cleaned.split("\n") if not l.startswith("```")])
            try:
                parsed = json.loads(cleaned)
            except Exception:
                repaired = cleaned
                repaired = re.sub(r'("[^"\n]*")\s*\n\s*("([a-zA-Z0-9_]+)"\s*:)', r'\1,\n\2', repaired)
                repaired = re.sub(r'([\d\.]+|true|false)\s*\n\s*("[\w_]+"\s*:)', r'\1,\n\2', repaired)
                repaired = re.sub(r',\s*([\}\]])', r'\1', repaired)
                parsed = json.loads(repaired)
            
            marks = float(parsed.get("total_marks", 0))
            max_marks = float(parsed.get("max_total_marks", 10))
            conf = float(parsed.get("overall_confidence", 0.8))
            feedback = parsed.get("feedback", "")
            await batch_mgr.update_paper_grade(jid, marks, max_marks, conf, feedback)
        except Exception as e:
            logger.error(f"[batch {batch_id}] Grading failed for {jid}: {e}")
            await batch_mgr.update_paper_grade(jid, 0, 10, 0.0, f"Grading error: {e}", error=str(e))

    try:
        await asyncio.to_thread(_ollama_generate, LOCAL_GRADING_MODEL, "", keep_alive=0)
    except Exception:
        pass
    
    await batch_mgr.set_batch_phase(batch_id, 2, "completed")
    logger.info(f"[batch {batch_id}] Phase 2 grading completed")


async def _process_staged_batch(batch_id: str, rubric: str, engine: str):
    logger.info(f"[batch {batch_id}] Executing batch with engine={engine}")
    status = await batch_mgr.get_status(batch_id)
    papers = status["papers"]

    # 1. Cloud Flash API Tier
    if engine == "cloud_flash" or (engine == "auto" and is_cloud_api_available()):
        logger.info(f"[batch {batch_id}] Processing via Cloud Flash API")
        await batch_mgr.set_batch_phase(batch_id, 1, "processing_cloud")
        for p in papers:
            jid = p["job_id"]
            img_path = p.get("file_path")
            try:
                raw_bytes = Path(img_path).read_bytes()
                res = await cloud_grade(raw_bytes, rubric)
                await batch_mgr.update_paper_ocr(jid, res.get("ocr_text", ""))
                await batch_mgr.update_paper_grade(
                    jid,
                    marks=res["total_marks"],
                    max_marks=res["max_total_marks"],
                    confidence=res["confidence"],
                    feedback=res["feedback"]
                )
            except Exception as e:
                logger.error(f"[batch {batch_id}] Paper {jid} failed on Cloud API: {e}")
                await batch_mgr.update_paper_grade(jid, 0, 10, 0.0, f"Cloud API error: {e}", error=str(e))
        await batch_mgr.set_batch_phase(batch_id, 2, "completed")
        return

    # 2. Remote Colab T4 Burst Tier
    if engine == "colab_burst" or (engine == "auto" and COLAB_INFERENCE_URL and await _colab_healthy()):
        logger.info(f"[batch {batch_id}] Processing via Colab T4 Burst backend")
        await batch_mgr.set_batch_phase(batch_id, 1, "processing_colab")
        for p in papers:
            jid = p["job_id"]
            img_path = p.get("file_path")
            try:
                raw_bytes = Path(img_path).read_bytes()
                b64 = base64.b64encode(raw_bytes).decode()
                res = await _colab_grade_endpoint(b64, rubric)
                norm = await _normalize_colab_result(res)
                await batch_mgr.update_paper_ocr(jid, norm.get("ocr_text", ""))
                await batch_mgr.update_paper_grade(
                    jid,
                    marks=norm.get("total_marks", 0),
                    max_marks=norm.get("max_total_marks", 10),
                    confidence=norm.get("overall_confidence", 0.8),
                    feedback=norm.get("feedback", "")
                )
            except Exception as e:
                logger.error(f"[batch {batch_id}] Paper {jid} failed on Colab: {e}")
                await batch_mgr.update_paper_grade(jid, 0, 10, 0.0, f"Colab error: {e}", error=str(e))
        await _colab_unload_models()
        await batch_mgr.set_batch_phase(batch_id, 2, "completed")
        return

    # 3. Two-Phase Staged Local Pipeline (Zero VRAM Thrashing on <=6GB laptops)
    logger.info(f"[batch {batch_id}] Processing via Staged Local Pipeline")
    await batch_mgr.set_batch_phase(batch_id, 1, "phase1_ocr")
    for p in papers:
        jid = p["job_id"]
        img_path = p.get("file_path")
        try:
            raw_bytes = Path(img_path).read_bytes()
            b64 = base64.b64encode(raw_bytes).decode()
            ocr_text = await asyncio.to_thread(
                _ollama_generate, LOCAL_OCR_MODEL, _ocr_prompt(),
                images=[b64], keep_alive=300, num_ctx=8192
            )
            await batch_mgr.update_paper_ocr(jid, ocr_text)
        except Exception as e:
            logger.error(f"[batch {batch_id}] Local OCR failed for {jid}: {e}")
            await batch_mgr.update_paper_ocr(jid, "", error=str(e))

    try:
        await asyncio.to_thread(_ollama_generate, LOCAL_OCR_MODEL, "", keep_alive=0)
    except Exception:
        pass

    await _process_phase2_grading(batch_id, rubric)


@app.post("/grade/batch")
async def create_batch_grade(
    files: List[UploadFile] = File(...),
    rubric: str = Form(default="Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity."),
    engine: str = Form(default="auto"),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    batch_items = []
    for f in files:
        raw_bytes = await f.read()
        if not raw_bytes:
            continue
        jid = uuid.uuid4().hex[:12]
        ext = Path(f.filename or "upload.jpg").suffix.lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp'}:
            ext = '.jpg'
        saved_path = UPLOAD_DIR / f"{jid}{ext}"
        saved_path.write_bytes(raw_bytes)

        try:
            img = Image.open(saved_path)
            w, h = img.size
            if max(w, h) > 1400:
                scale = 1400.0 / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                img = img.resize(new_size, Image.LANCZOS)
                jpeg_path = UPLOAD_DIR / f"{jid}.jpg"
                img.save(jpeg_path, "JPEG", quality=85, optimize=True)
                if saved_path != jpeg_path and saved_path.exists():
                    saved_path.unlink()
                saved_path = jpeg_path
        except Exception as e:
            logger.warning(f"Image preprocessing warning for {f.filename}: {e}")

        batch_items.append({
            "job_id": jid,
            "filename": f.filename or f"{jid}.jpg",
            "file_path": str(saved_path)
        })

    if not batch_items:
        raise HTTPException(status_code=400, detail="No valid image files uploaded")

    batch_id = await batch_mgr.create_batch(batch_items, rubric=rubric, engine=engine)
    asyncio.create_task(_process_staged_batch(batch_id, rubric, engine))

    return JSONResponse(
        status_code=202,
        content={
            "batch_id": batch_id,
            "total_papers": len(batch_items),
            "engine": engine,
            "status": "queued",
            "message": "Batch accepted and processing in background"
        }
    )


@app.get("/grade/batch/{batch_id}")
async def get_batch_status(batch_id: str):
    try:
        return await batch_mgr.get_status(batch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/grade/batch/{batch_id}/regrade")
async def regrade_batch(
    batch_id: str,
    rubric: str = Form(...)
):
    try:
        await batch_mgr.reset_batch_for_regrade(batch_id, rubric)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    asyncio.create_task(_process_phase2_grading(batch_id, rubric))
    return JSONResponse(
        status_code=202,
        content={
            "batch_id": batch_id,
            "status": "phase2_grading",
            "message": "Re-grading started using cached OCR transcripts"
        }
    )

# ---------------------------------------------------------------------------
# Pairing & Mobile API
# ---------------------------------------------------------------------------


class PairRequest(BaseModel):
    base_url: str  # e.g., "https://xxx.pinggy.link"


@app.get("/api/pair")
def create_pair(request: PairRequest, token: str = Depends(verify_token)):
    """Generate pairing QR data for mobile app."""
    pair_token = secrets.token_urlsafe(16)
    expires = datetime.now() + timedelta(hours=24)

    PAIRING_TOKENS[pair_token] = {
        "url": request.base_url.rstrip("/"),
        "expires": expires,
        "created": datetime.now(),
    }

    qr_data = f"inscrona://pair?url={request.base_url.rstrip('/')}&token={pair_token}"

    logger.info(f"Generated pairing token for {request.base_url}")
    return {
        "token": pair_token,
        "url": request.base_url.rstrip("/"),
        "expires_at": expires.isoformat(),
        "qr_data": qr_data,
    }


@app.get("/api/health")
def mobile_health(token: str = Depends(verify_token)):
    """Health check for paired mobile clients."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        return {
            "status": "ok",
            "models": {
                "ocr": {"name": "glm-ocr", "loaded": "glm-ocr:latest" in models},
                "grading": {"name": "llama3.2:3b", "loaded": "llama3.2:3b" in models},
            },
            "version": "0.1.0",
        }
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.post("/api/grade", response_model=GradeResult)
async def mobile_grade(
    file: UploadFile = File(...),
    rubric: str = Form(default="Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity."),
    token: str = Depends(verify_token),
):
    """Mobile-optimized grading endpoint with progress via WebSocket."""
    job_id = uuid.uuid4().hex[:12]
    logger.info(f"[{job_id}] Mobile grading request -- file={file.filename}")

    # Notify WebSocket clients: uploading
    _broadcast_progress(job_id, {
        "stage": "uploading",
        "progress": 10,
        "message": "Receiving image...",
    })

    # -- 1. Save uploaded image --
    raw_bytes = await file.read()
    ext = Path(file.filename or "upload.jpg").suffix.lower()
    saved_path = UPLOAD_DIR / f"{job_id}{ext}"
    saved_path.write_bytes(raw_bytes)
    logger.info(f"[{job_id}] Saved upload to {saved_path} ({len(raw_bytes)} bytes)")

    _broadcast_progress(job_id, {
        "stage": "uploading",
        "progress": 30,
        "message": "Processing image...",
    })

    # -- 2. Convert HEIC to JPEG and resize --
    try:
        img = Image.open(saved_path)
        if ext in (".heic", ".heif"):
            jpeg_path = UPLOAD_DIR / f"{job_id}.jpg"
            img.save(jpeg_path, "JPEG", quality=90)
            saved_path.unlink()
            saved_path = jpeg_path
            logger.info(f"[{job_id}] Converted HEIC to JPEG: {saved_path}")
    except Exception as e:
        logger.error(f"[{job_id}] Failed to open image: {e}")
        raise HTTPException(status_code=400, detail=f"Cannot open image: {e}")

    if max(img.size) > MAX_LONGEST_EDGE:
        scale = MAX_LONGEST_EDGE / max(img.size)
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)
        img.save(saved_path, "JPEG", quality=90)
        logger.info(f"[{job_id}] Resized {img.size[0]}x{img.size[1]} -> {new_size[0]}x{new_size[1]}")

    _broadcast_progress(job_id, {
        "stage": "ocr",
        "progress": 40,
        "message": "Loading GLM-OCR...",
    })

    # -- 3. Convert image to base64 for inference --
    with open(saved_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    # -- 4. Run inference with fallback (local -> Colab) --
    _broadcast_progress(job_id, {
        "stage": "ocr",
        "progress": 50,
        "message": "Running inference (local first, Colab fallback)...",
    })
    
    try:
        result = await _grade_with_fallback(image_b64, rubric, job_id)
    except Exception as e:
        logger.error(f"[{job_id}] All inference failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    # Ensure all required fields
    result.setdefault("ocr_text", "")
    parsed = GradeResult(**result)

    # -- 6. Save result --
    result_path = RESULT_DIR / f"{job_id}_grade.json"
    result_dict = result.model_dump()
    result_dict["processing_time_ms"] = 0  # TODO: track actual time
    result_path.write_text(json.dumps(result_dict, indent=2), encoding="utf-8")
    logger.info(f"[{job_id}] Saved grade to {result_path}")

    _broadcast_progress(job_id, {
        "stage": "completed",
        "progress": 100,
        "message": "Complete!",
        "result": result_dict,
    })

    return result


@app.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket, token: str):
    """WebSocket for real-time grading progress."""
    try:
        await ws_auth(websocket, token)
    except HTTPException:
        return

    await websocket.accept()

    # Register this websocket for all job_ids (client will filter)
    # In practice, client sends job_id after connecting
    try:
        while True:
            data = await websocket.receive_json()
            # Client sends: {"job_id": "xxx", "action": "subscribe"}
            if data.get("action") == "subscribe" and "job_id" in data:
                job_id = data["job_id"]
                if job_id not in ACTIVE_WS:
                    ACTIVE_WS[job_id] = set()
                ACTIVE_WS[job_id].add(websocket)
                logger.debug(f"WS subscribed to {job_id}")
    except WebSocketDisconnect:
        # Clean up
        for job_id, sockets in ACTIVE_WS.items():
            sockets.discard(websocket)
        logger.debug("WS disconnected")


def _broadcast_progress(job_id: str, progress: dict):
    """Send progress update to all WebSocket subscribers for a job."""
    if job_id in ACTIVE_WS:
        dead = set()
        for ws in ACTIVE_WS[job_id]:
            try:
                import asyncio
                asyncio.create_task(ws.send_json(progress))
            except Exception:
                dead.add(ws)
        for ws in dead:
            ACTIVE_WS[job_id].discard(ws)

def _ollama_generate(
    model: str,
    prompt: str,
    images: list[str] | None = None,
    keep_alive: int = 0,
    format_json: bool = False,
    timeout: int = 600,
    num_ctx: int | None = None,
    num_predict: int = 2048,
) -> str:
    """Call Ollama /api/generate with streaming, return full response text.

    num_ctx caps the context window (default: server decides = model native
    131072 for glm-ocr, whose 4 GiB KV cache OOM-crashes the 8 GiB RX 6600M
    via Vulkan — see PROGRESS.md Wave 0 verdict). Always pass an explicit
    num_ctx (8192 for OCR, 4096 for grading).
    """
    options: dict = {"num_predict": num_predict, "temperature": 0.1}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    num_gpu_env = os.getenv("OLLAMA_NUM_GPU")
    if num_gpu_env is not None:
        try:
            options["num_gpu"] = int(num_gpu_env)
        except ValueError:
            pass
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "keep_alive": keep_alive,
        "stream": True,
        "options": options,
    }
    if images:
        payload["images"] = images
    if format_json:
        payload["format"] = "json"

    start = time.time()
    resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=timeout)
    resp.raise_for_status()
    full: list[str] = []
    for line in resp.iter_lines():
        if line:
            chunk = json.loads(line)
            full.append(chunk.get("response", ""))
            if chunk.get("done"):
                break
    elapsed = time.time() - start
    logger.debug(f"  [{model}] {elapsed:.1f}s, {len(''.join(full))} chars")
    return "".join(full)


# ---------------------------------------------------------------------------
# Colab Remote Inference Fallback
# ---------------------------------------------------------------------------
COLAB_INFERENCE_URL = os.getenv("COLAB_INFERENCE_URL", "").rstrip("/")
# Short fail-fast probe for burst mode — never the 600s grade timeout.
COLAB_HEALTH_TIMEOUT_S = 8
# Circuit breaker: 3 consecutive Colab failures -> OPEN, 60s half-open probe.
COLAB_BREAKER_THRESHOLD = 3
COLAB_BREAKER_COOLDOWN_S = 60
# In-memory like PAIRING_TOKENS: a restart resets to CLOSED (documented).
_colab_breaker = {"state": "CLOSED", "failures": 0, "opened_at": 0.0}


def _breaker_allows() -> bool:
    """True when a Colab attempt may proceed (CLOSED or cooled-down OPEN)."""
    s = _colab_breaker
    if s["state"] == "CLOSED":
        return True
    if time.time() - s["opened_at"] >= COLAB_BREAKER_COOLDOWN_S:
        s["state"] = "HALF-OPEN"
        return True
    return False


def _breaker_success() -> None:
    s = _colab_breaker
    s["state"] = "CLOSED"
    s["failures"] = 0


def _breaker_failure() -> bool:
    """Record a Colab failure. Returns True when the breaker just OPENED."""
    s = _colab_breaker
    s["failures"] += 1
    if s["failures"] >= COLAB_BREAKER_THRESHOLD and s["state"] != "OPEN":
        s["state"] = "OPEN"
        s["opened_at"] = time.time()
        return True
    return False


def _breaker_reset() -> None:
    """Test/support hook: force the breaker back to CLOSED."""
    _colab_breaker.update({"state": "CLOSED", "failures": 0, "opened_at": 0.0})


def _current_mode() -> str:
    """Advertised inference mode: hybrid only when Colab is configured and
    the breaker is not OPEN; otherwise local-only."""
    if COLAB_INFERENCE_URL and _colab_breaker["state"] != "OPEN":
        return "hybrid"
    return "local-only"


async def _colab_unload_models() -> None:
    """Best-effort zero-resident discipline on the burst backend: ask the
    Colab daemon to unload both models after a burst paper. Fire-and-forget —
    failures are logged at debug and never fail the grade."""
    url = COLAB_INFERENCE_URL
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for model in ("glm-ocr", "llama3.2:3b"):
                try:
                    await client.post(f"{url}/api/generate",
                                      json={"model": model, "keep_alive": 0})
                except Exception as e:
                    logger.debug(f"Colab unload hint for {model} failed (ignored)")
    except Exception:
        pass


async def _colab_healthy() -> bool:
    """Fast health probe for the Colab burst backend.

    Returns False on any failure. Never raises, and never logs the tunnel
    URL (it is a bearer secret — see PLAN.md threat-model note). Probe
    outcomes feed the circuit breaker.
    """
    url = COLAB_INFERENCE_URL
    if not url or not _breaker_allows():
        return False
    try:
        async with httpx.AsyncClient(timeout=COLAB_HEALTH_TIMEOUT_S) as client:
            resp = await client.get(f"{url}/health")
            ok = resp.status_code == 200
    except Exception:
        ok = False
    if ok:
        _breaker_success()
    else:
        _breaker_failure()
    return ok


async def _normalize_colab_result(result: dict) -> dict:
    """Map the Colab /grade schema onto the local GradeResult shape.

    Colab returns the legacy keys {marks, confidence, feedback, ocr_text};
    local code expects {total_marks, max_total_marks, overall_confidence,
    confidence_level, question_grades, flags, ...}. Missing keys get safe
    defaults; `percentage` is recomputed server-side later in grade().
    New-schema dicts pass through untouched.
    """
    if not isinstance(result, dict):
        raise ValueError("Colab response is not a JSON object")
    if "total_marks" in result or "overall_confidence" in result:
        result.setdefault("max_total_marks", 10)
        result.setdefault("confidence_level", "medium")
        result.setdefault("question_grades", [])
        result.setdefault("flags", [])
        result.setdefault("model_used", "colab_fallback")
        result.setdefault("fallback_used", True)
        result.setdefault("ocr_text", "")
        return result
    flags = list(result.get("flags", []) or [])
    flags.append("colab_legacy_schema")
    conf = result.get("confidence", 0.5)
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.5
    return {
        "total_marks": result.get("marks", 0),
        "max_total_marks": result.get("max_total_marks", 10),
        "overall_confidence": conf,
        "confidence_level": (
            "high" if conf >= 0.75 else "low" if conf < 0.4 else "medium"
        ),
        "feedback": result.get("feedback", ""),
        "question_grades": result.get("question_grades", []),
        "ocr_text": result.get("ocr_text", ""),
        "model_used": result.get("model_used", "colab_fallback"),
        "fallback_used": True,
        "flags": flags,
    }


async def _colab_grade_endpoint(image_b64: str, rubric: str) -> dict:
    """Call Colab /grade endpoint for full OCR + grading pipeline."""
    if not COLAB_INFERENCE_URL:
        raise RuntimeError("COLAB_INFERENCE_URL not configured")
    
    import httpx
    
    # Decode base64 image
    image_bytes = base64.b64decode(image_b64)
    
    async with httpx.AsyncClient(timeout=600) as client:
        files = {"file": ("image.jpg", image_bytes, "image/jpeg")}
        data = {"rubric": rubric}
        
        resp = await client.post(
            f"{COLAB_INFERENCE_URL}/grade",
            files=files,
            data=data,
            timeout=600
        )
        resp.raise_for_status()
        return resp.json()


async def _grade_with_fallback(
    image_b64: str,
    rubric: str,
    job_id: str,
    return_question_breakdown: bool = True,
    burst: bool = False,
    warm: bool = False,
) -> dict:
    """
    Try local Ollama first, fallback to Colab on failure.
    With burst=True, Colab is tried FIRST when its health probe passes;
    otherwise degrade to local with a `burst_unavailable` flag (never a 500).
    With warm=True, the burst session is prime-verified and the backend is
    asked to unload models after the paper (zero-resident discipline).
    Returns parsed result dict with structured grading output.
    """
    # Burst opt-in: Colab primary when healthy (skip slow local OCR)
    if burst:
        if _breaker_allows() and await _colab_healthy():
            logger.info(f"[{job_id}] Burst mode: Colab healthy, using burst primary...")
            _broadcast_progress(job_id, {"stage": "ocr", "progress": 20, "message": "Burst OCR (Colab)..."})
            try:
                if warm:
                    await _colab_healthy()  # prime = second confirmation
                result = await _colab_grade_endpoint(image_b64, rubric)
                _breaker_success()
                logger.info(f"[{job_id}] Burst primary succeeded")
                out = await _normalize_colab_result(result)
                flags = out.setdefault("flags", [])
                if warm and "warmed" not in flags:
                    flags.append("warmed")
                await _colab_unload_models()
                return out
            except Exception:
                _breaker_failure()
                logger.warning(f"[{job_id}] Burst primary failed, degrading to local")
        elif _colab_breaker["state"] == "OPEN":
            logger.info(f"[{job_id}] Burst requested but circuit OPEN — instant local path")
        else:
            logger.info(f"[{job_id}] Burst requested but Colab unreachable — local path")
    burst_degraded = burst

    # Try local first (blocking Ollama calls run in a worker thread so the
    # event loop stays free for /health, /results and concurrent grades)
    try:
        logger.info(f"[{job_id}] Attempting local Ollama inference...")
        
        # OCR
        _broadcast_progress(job_id, {"stage": "ocr", "progress": 20, "message": "Local OCR (GLM-OCR)..."})
        ocr_text = await asyncio.to_thread(
            _ollama_generate, LOCAL_OCR_MODEL, _ocr_prompt(),
            images=[image_b64], keep_alive=0, num_ctx=8192,
        )
        
        _broadcast_progress(job_id, {"stage": "grading", "progress": 50, "message": "Local grading (Llama 3.2)..."})
        grade_prompt = GRADING_PROMPT_TEMPLATE.format(ocr_text=ocr_text, rubric=rubric)
        grade_raw = await asyncio.to_thread(
            _ollama_generate, LOCAL_GRADING_MODEL, grade_prompt,
            keep_alive=0, format_json=True, num_ctx=4096,
            num_predict=GRADE_NUM_PREDICT,
        )
        
        # Parse structured response
        cleaned = grade_raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join([l for l in cleaned.split("\n") if not l.startswith("```")])
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as decode_err:
            logger.warning(f"[{job_id}] Initial JSON parse failed ({decode_err}); attempting standard-library repair...")
            repaired = cleaned
            repaired = re.sub(r'("[^"\n]*")\s*\n\s*("([a-zA-Z0-9_]+)"\s*:)', r'\1,\n\2', repaired)
            repaired = re.sub(r'([\d\.]+|true|false)\s*\n\s*("[\w_]+"\s*:)', r'\1,\n\2', repaired)
            repaired = re.sub(r'(\}\s*)\n(\s*\{)', r'\1,\n\2', repaired)
            repaired = re.sub(r',\s*([\}\]])', r'\1', repaired)
            open_braces = repaired.count('{') - repaired.count('}')
            open_brackets = repaired.count('[') - repaired.count(']')
            if open_brackets > 0:
                repaired += ']' * open_brackets
            if open_braces > 0:
                repaired += '}' * open_braces
            parsed = json.loads(repaired)
            logger.info(f"[{job_id}] JSON auto-repair succeeded")
        
        # Validate required fields
        required = ["total_marks", "max_total_marks", "percentage", "overall_confidence", "confidence_level", "feedback"]
        for field in required:
            if field not in parsed:
                raise ValueError(f"Missing required field: {field}")
        
        logger.info(f"[{job_id}] Local inference succeeded")
        flags = parsed.setdefault("flags", [])
        if burst_degraded and "burst_unavailable" not in flags:
            flags.append("burst_unavailable")
        if _colab_breaker["state"] == "OPEN" and "colab_circuit_open" not in flags:
            flags.append("colab_circuit_open")
        return {
            **parsed,
            "ocr_text": ocr_text,
            "model_used": "glm-ocr + llama3.2:3b (local)",
            "fallback_used": False,
        }
        
    except Exception as e:
        logger.warning(f"[{job_id}] Local inference failed: {e}")
        
        if not COLAB_INFERENCE_URL:
            raise RuntimeError(f"Local inference failed and no Colab fallback configured: {e}")
        if not _breaker_allows():
            raise RuntimeError(f"Local inference failed; Colab circuit OPEN, skipped: {e}")

        # Fallback to Colab (tunnel URL never logged — bearer secret)
        logger.info(f"[{job_id}] Falling back to Colab burst backend")
        _broadcast_progress(job_id, {"stage": "ocr", "progress": 10, "message": "Local failed, trying Colab..."})

        try:
            result = await _colab_grade_endpoint(image_b64, rubric)
            _breaker_success()
            logger.info(f"[{job_id}] Colab fallback succeeded")
            # Normalize legacy Colab keys onto the GradeResult shape
            return await _normalize_colab_result(result)
        except Exception as colab_e:
            _breaker_failure()
            logger.error(f"[{job_id}] Colab fallback also failed")
            raise RuntimeError(f"Both local and Colab inference failed. Local: {e}, Colab: {colab_e}")
