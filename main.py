"""Inscrona FastAPI backend — sequential OCR + grading pipeline."""
import base64
import csv
import io
import json
import os
import time
import uuid
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Set

import pillow_heif
import requests
import sentry_sdk
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Sentry initialization
# ---------------------------------------------------------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=os.getenv("ENVIRONMENT", "development"),
    )
    logger.info("Sentry initialized")
else:
    logger.warning("SENTRY_DSN not set — Sentry disabled")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OLLAMA_URL = "http://127.0.0.1:11434"
UPLOAD_DIR = Path("./uploads")
RESULT_DIR = Path("./results")
MAX_LONGEST_EDGE = 2000

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# Register HEIC opener with Pillow
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
# Pydantic schema for grading output
# ---------------------------------------------------------------------------

class GradeResult(BaseModel):
    marks: int
    confidence: float
    feedback: str
    ocr_text: str

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Inscrona", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


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
                "marks": data.get("marks", 0),
                "confidence": data.get("confidence", 0),
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
                    data.get("marks", ""),
                    data.get("confidence", ""),
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
    return data


@app.post("/grade", response_model=GradeResult)
async def grade(
    file: UploadFile = File(...),
    rubric: str = Form(default="Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity."),
):
    job_id = uuid.uuid4().hex[:12]
    logger.info(f"[{job_id}] Received grading request -- file={file.filename}")

    # -- 1. Save uploaded image --
    raw_bytes = await file.read()
    ext = Path(file.filename or "upload.jpg").suffix.lower()
    saved_path = UPLOAD_DIR / f"{job_id}{ext}"
    saved_path.write_bytes(raw_bytes)
    logger.info(f"[{job_id}] Saved upload to {saved_path} ({len(raw_bytes)} bytes)")

    # -- 2. Convert HEIC to JPEG and resize --
    try:
        img = Image.open(saved_path)
        if ext in (".heic", ".heif"):
            jpeg_path = UPLOAD_DIR / f"{job_id}.jpg"
            img.save(jpeg_path, "JPEG", quality=90)
            saved_path.unlink()  # remove HEIC
            saved_path = jpeg_path
            logger.info(f"[{job_id}] Converted HEIC to JPEG: {saved_path}")
    except Exception as e:
        logger.error(f"[{job_id}] Failed to open image: {e}")
        raise HTTPException(status_code=400, detail=f"Cannot open image: {e}")

    # Resize if too large
    w, h = img.size
    if max(w, h) > MAX_LONGEST_EDGE:
        scale = MAX_LONGEST_EDGE / max(w, h)
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
        img.save(saved_path, "JPEG", quality=90)
        logger.info(f"[{job_id}] Resized {w}x{h} -> {new_size[0]}x{new_size[1]}")

    # -- 3. OCR with glm-ocr --
    logger.info(f"[{job_id}] Loading glm-ocr for OCR extraction...")
    with open(saved_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    ocr_prompt = (
        "Extract all text from this answer booklet image. "
        "Output only the text content, preserving layout as much as possible."
    )
    ocr_text = _ollama_generate("glm-ocr", ocr_prompt, images=[image_b64], keep_alive=0)
    logger.info(f"[{job_id}] OCR completed ({len(ocr_text)} chars)")

    # -- 4. Grade with llama3.2:3b --
    logger.info(f"[{job_id}] Loading llama3.2:3b for grading...")
    grade_prompt = (
        f"You are an exam grading assistant. Grade the following student answer.\n\n"
        f"Student Answer:\n{ocr_text}\n\n"
        f"Rubric: {rubric}\n\n"
        f"Respond ONLY with valid JSON in this exact format:\n"
        f'{{"marks": <0-10>, "confidence": <0.0-1.0>, "feedback": "<brief assessment>"}}'
    )
    grade_raw = _ollama_generate("llama3.2:3b", grade_prompt, keep_alive=0, format_json=True)
    logger.info(f"[{job_id}] Grading completed ({len(grade_raw)} chars)")

    # -- 5. Parse JSON --
    try:
        cleaned = grade_raw.strip()
        if cleaned.startswith("```"):
            lines = [l for l in cleaned.split("\n") if not l.startswith("```")]
            cleaned = "\n".join(lines)
        parsed = json.loads(cleaned)

        # Handle marks as dict (per-question breakdown) -> extract average
        marks_raw = parsed.get("marks", 0)
        if isinstance(marks_raw, dict):
            values = [v for v in marks_raw.values() if isinstance(v, (int, float))]
            parsed["marks"] = round(sum(values) / len(values)) if values else 0
            logger.info(f"[{job_id}] Marks dict flattened to avg: {parsed['marks']}")
        elif isinstance(marks_raw, str):
            parsed["marks"] = int(marks_raw)

        # Handle confidence as percentage string like "80%"
        conf_raw = parsed.get("confidence", 0.5)
        if isinstance(conf_raw, str):
            conf_raw = conf_raw.replace("%", "").strip()
            parsed["confidence"] = float(conf_raw) / 100.0 if float(conf_raw) > 1 else float(conf_raw)

        parsed["ocr_text"] = ocr_text
        result = GradeResult(**parsed)
    except Exception as e:
        logger.error(f"[{job_id}] JSON parse failed: {e}")
        raise HTTPException(status_code=500, detail=f"Grading model returned invalid JSON: {e}")

    # -- 6. Save result --
    result_path = RESULT_DIR / f"{job_id}_grade.json"
    result_path.write_text(json.dumps(result.model_dump(), indent=2), encoding="utf-8")
    logger.info(f"[{job_id}] Saved grade to {result_path}")

    return result


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
) -> str:
    """Call Ollama /api/generate with streaming, return full response text."""
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "keep_alive": keep_alive,
        "stream": True,
        "options": {"num_predict": 2048, "temperature": 0.1},
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


async def _colab_generate(model: str, prompt: str, images=None, keep_alive=0, format_json=False, timeout=600) -> str:
    """Call Colab remote inference endpoint."""
    if not COLAB_INFERENCE_URL:
        raise RuntimeError("COLAB_INFERENCE_URL not configured")
    
    # For remote, we need to send the image as base64 in the prompt context
    # The Colab endpoint expects multipart form with file + rubric
    # This is a simplified version - full implementation would call /grade endpoint
    raise NotImplementedError("Use _colab_grade_endpoint for full pipeline")


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
) -> dict:
    """
    Try local Ollama first, fallback to Colab on failure.
    Returns parsed result dict with marks, confidence, feedback, ocr_text.
    """
    # Try local first
    try:
        logger.info(f"[{job_id}] Attempting local Ollama inference...")
        
        # OCR
        _broadcast_progress(job_id, {"stage": "ocr", "progress": 20, "message": "Local OCR (GLM-OCR)..."})
        ocr_text = _ollama_generate("glm-ocr", 
            "Extract all text from this answer booklet image. Output only the text content, preserving layout.",
            images=[image_b64], keep_alive=0)
        
        _broadcast_progress(job_id, {"stage": "grading", "progress": 50, "message": "Local grading (Llama 3.2)..."})
        grade_prompt = (
            f"You are an exam grading assistant. Grade the following student answer.\n\n"
            f"Student Answer:\n{ocr_text}\n\n"
            f"Rubric: {rubric}\n\n"
            f"Respond ONLY with valid JSON:\n"
            f'{{"marks": <0-10>, "confidence": <0.0-1.0>, "feedback": "<brief assessment>"}}'
        )
        grade_raw = _ollama_generate("llama3.2:3b", grade_prompt, keep_alive=0, format_json=True)
        
        # Parse
        cleaned = grade_raw.strip()
        if cleaned.startswith("```"):
            cleaned = "\n".join([l for l in cleaned.split("\n") if not l.startswith("```")])
        parsed = json.loads(cleaned)
        
        marks = parsed.get("marks", 0)
        if isinstance(marks, dict):
            vals = [v for v in marks.values() if isinstance(v, (int, float))]
            marks = round(sum(vals)/len(vals)) if vals else 0
        elif isinstance(marks, str):
            marks = int(marks)
        
        conf = parsed.get("confidence", 0.5)
        if isinstance(conf, str):
            conf = conf.replace("%", "").strip()
            conf = float(conf)/100.0 if float(conf) > 1 else float(conf)
        
        logger.info(f"[{job_id}] Local inference succeeded")
        return {
            "marks": marks,
            "confidence": conf,
            "feedback": parsed.get("feedback", ""),
            "ocr_text": ocr_text
        }
        
    except Exception as e:
        logger.warning(f"[{job_id}] Local inference failed: {e}")
        
        if not COLAB_INFERENCE_URL:
            raise RuntimeError(f"Local inference failed and no Colab fallback configured: {e}")
        
        # Fallback to Colab
        logger.info(f"[{job_id}] Falling back to Colab: {COLAB_INFERENCE_URL}")
        _broadcast_progress(job_id, {"stage": "ocr", "progress": 10, "message": "Local failed, trying Colab..."})
        
        try:
            result = await _colab_grade_endpoint(image_b64, rubric)
            logger.info(f"[{job_id}] Colab fallback succeeded")
            return result
        except Exception as colab_e:
            logger.error(f"[{job_id}] Colab fallback also failed: {colab_e}")
            raise RuntimeError(f"Both local and Colab inference failed. Local: {e}, Colab: {colab_e}")
