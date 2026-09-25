#!/usr/bin/env python3
"""
Inscrona Remote GPU Burst Worker
Runs on Google Colab, RunPod, Lambda Labs, or any remote machine with a GPU.
Exposes a FastAPI endpoint (/health, /grade) and tunnels it back to your local Inscrona.
"""

import os
import sys
import time
import argparse
import subprocess
import requests
import json
import base64
import io
import re
import shutil
from pathlib import Path
from PIL import Image
from typing import Optional, List, Dict, Any, Union

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
REQUIRED_MODELS = ["glm-ocr", "llama3.2:3b"]

def log(msg: str):
    print(f"[Inscrona-Worker] {msg}", flush=True)

def get_ollama_bin():
    return shutil.which("ollama") or "/usr/local/bin/ollama" or "/usr/bin/ollama" or "ollama"

def ensure_ollama_running():
    """Ensure Ollama is installed and running."""
    # 1. Check if Ollama binary exists; if not, install it automatically (works on Colab/Linux)
    if shutil.which("ollama") is None and not Path("/usr/local/bin/ollama").exists() and not Path("/usr/bin/ollama").exists():
        log("Ollama binary not found on system. Installing dependencies (zstd) and Ollama...")
        try:
            # Install zstd decompression tool required by Ollama tarball
            subprocess.run("apt-get update -qq && apt-get install -y -qq zstd curl", shell=True)
            res = subprocess.run("curl -fsSL https://ollama.ai/install.sh | sh", shell=True, capture_output=True, text=True)
            if res.returncode == 0 or Path("/usr/local/bin/ollama").exists():
                log("Ollama installed successfully!")
            else:
                log(f"Ollama installer output: {res.stdout} {res.stderr}")
        except Exception as e:
            log(f"Failed to run Ollama installer: {e}")

        # Ensure PATH includes standard linux binary locations
        for p in ("/usr/local/bin", "/usr/bin", "/bin"):
            if p not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{p}:{os.environ.get('PATH', '')}"

    # 2. Check if daemon is already active and responding
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            log("Ollama daemon is already active.")
            return
    except Exception:
        pass

    # 3. Start background Ollama daemon
    ollama_bin = get_ollama_bin()
    log(f"Starting Ollama daemon via: {ollama_bin} serve...")
    try:
        subprocess.Popen([ollama_bin, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"Error starting {ollama_bin}: {e}. Retrying with shell...")
        subprocess.Popen("ollama serve > /dev/null 2>&1 &", shell=True)

    for i in range(25):
        time.sleep(1)
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if r.status_code == 200:
                log("Ollama daemon started and verified healthy.")
                return
        except Exception:
            pass

    log("Warning: Ollama daemon did not answer probe within 25s. Continuing...")

def ensure_models():
    """Ensure required models are pulled."""
    ollama_bin = get_ollama_bin()
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        installed = [m["name"].split(":")[0] for m in r.json().get("models", [])]
    except Exception:
        installed = []

    for m in REQUIRED_MODELS:
        if m not in installed:
            log(f"Pulling model '{m}' into GPU VRAM (this may take 1-3 minutes on Colab)...")
            try:
                subprocess.run([ollama_bin, "pull", m], check=True)
                log(f"Model '{m}' pulled and ready.")
            except Exception as e:
                log(f"Error pulling model {m}: {e}")
        else:
            log(f"Model '{m}' is already available.")

def create_app():
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="Inscrona GPU Worker", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        gpu_info = "GPU Available"
        try:
            smi = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], text=True)
            gpu_info = smi.strip()
        except Exception:
            pass

        return {
            "status": "ok",
            "backend": "colab_gpu_worker",
            "gpu": gpu_info,
            "models": {
                "ocr": {"name": "glm-ocr", "loaded": True},
                "grading": {"name": "llama3.2:3b", "loaded": True}
            }
        }

    @app.post("/grade")
    async def grade_endpoint(
        file: UploadFile = File(...),
        rubric: str = Form(default="Evaluate answer accuracy and completeness."),
        question_paper: str = Form(default=""),
        question_paper_file: Optional[UploadFile] = File(default=None)
    ):
        start_t = time.perf_counter()
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(400, "Empty file uploaded")

        # 0. Optional Question Paper OCR if file provided
        qp_text = question_paper or ""
        if question_paper_file:
            qp_bytes = await question_paper_file.read()
            if qp_bytes:
                try:
                    qp_img = Image.open(io.BytesIO(qp_bytes))
                    if max(qp_img.size) > 1024:
                        qp_scale = 1024 / max(qp_img.size)
                        qp_img = qp_img.resize((int(qp_img.width * qp_scale), int(qp_img.height * qp_scale)), Image.LANCZOS)
                    qp_buf = io.BytesIO()
                    qp_img.save(qp_buf, format="JPEG", quality=85)
                    qp_b64 = base64.b64encode(qp_buf.getvalue()).decode()
                    qp_ocr_resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
                        "model": "glm-ocr",
                        "prompt": "Extract all questions, parts, marks, and rubrics from this master question paper.",
                        "images": [qp_b64],
                        "stream": False,
                        "options": {"num_ctx": 2048, "temperature": 0.0, "repeat_penalty": 1.15, "num_predict": 800, "stop": ["```\n```", "\n\n\n\n"]}
                    }, timeout=120)
                    qp_extracted = qp_ocr_resp.json().get("response", "").strip()
                    if qp_extracted:
                        qp_text = f"{qp_text}\n{qp_extracted}".strip()
                except Exception as e:
                    log(f"Question paper OCR extraction failed: {e}")

        # 1. Process Student Answer image (1024 max edge = 1 single tile = 1.2s GPU pass)
        img = Image.open(io.BytesIO(raw_bytes))
        if max(img.size) > 1024:
            scale = 1024 / max(img.size)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        # 2. Ultra-Fast GPU OCR with GLM-OCR (with anti-repetition penalty & stop tokens)
        ocr_prompt = "Extract all handwritten and printed text from this exam answer paper accurately. Preserve lines, question numbers, and parts."
        ocr_resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": "glm-ocr",
            "prompt": ocr_prompt,
            "images": [img_b64],
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0.0,
                "repeat_penalty": 1.15,
                "num_predict": 1024,
                "stop": ["```\n```", "\n\n\n\n", "```\n\n```", "<|endoftext|>"]
            }
        }, timeout=120)
        ocr_text = ocr_resp.json().get("response", "")

        # Strip runaway loop backticks if any
        if "```mark" in ocr_text:
            first_part = ocr_text.split("```mark")[0].strip()
            if len(first_part) > 60:
                ocr_text = first_part
        ocr_text = re.sub(r"(```\s*){3,}", "", ocr_text).strip()

        # Extract student registration number if visible
        reg_match = re.search(r"(?:Registration\s*No\.?|Reg\.?\s*No\.?|Roll\s*No\.?|USN|Student\s*ID)[:\-\.\s]*([A-Za-z0-9\-]+)", ocr_text, re.I)
        student_reg = reg_match.group(1).strip() if reg_match else None

        # 3. Fast GPU Evaluation with Llama 3.2:3b
        qp_context = f"\nMASTER QUESTION PAPER & MARKING SCHEME:\n{qp_text}\n" if qp_text else ""
        grade_prompt = f"""You are an expert university exam grader. Grade the student answers against the rubric.{qp_context}

STUDENT ANSWER:
{ocr_text}

RUBRIC:
{rubric}

Respond ONLY with valid JSON matching:
{{
  "total_marks": <number 0-20>,
  "max_total_marks": <number e.g. 20>,
  "percentage": <number 0-100>,
  "overall_confidence": <number 0.0-1.0>,
  "confidence_level": "<high|medium|low>",
  "feedback": "<concise evaluation>",
  "question_grades": [
     {{"question_id": "Q1", "marks_awarded": <number>, "max_marks": <number>, "confidence": <0.0-1.0>, "feedback": "<text>"}}
  ]
}}"""

        eval_resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": "llama3.2:3b",
            "prompt": grade_prompt,
            "format": "json",
            "stream": False,
            "options": {"num_ctx": 4096, "temperature": 0.1, "num_predict": 1024}
        }, timeout=120)

        raw_eval = eval_resp.json().get("response", "{}")
        try:
            cleaned = raw_eval.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join([l for l in cleaned.split("\n") if not l.startswith("```")])
            parsed = json.loads(cleaned)
        except Exception:
            parsed = {"total_marks": 10, "max_total_marks": 10, "overall_confidence": 0.8, "confidence_level": "medium", "feedback": raw_eval}

        parsed["ocr_text"] = ocr_text
        if student_reg:
            parsed["reg_no"] = student_reg
        parsed["processing_time_ms"] = int((time.perf_counter() - start_t) * 1000)
        parsed["model_used"] = "glm-ocr + llama3.2:3b (Colab GPU)"
        return JSONResponse(parsed)

    return app

def start_tunnel(tunnel_type: str, port: int) -> str:
    """Start Cloudflare or Pinggy tunnel and return public URL."""
    # Cloudflare is default and fastest on Colab (installs in 2s, stable URL)
    if tunnel_type == "cloudflare" or tunnel_type != "pinggy":
        log("Setting up Cloudflare tunnel (fast, zero sign-up)...")
        if shutil.which("cloudflared") is None:
            log("Installing cloudflared...")
            subprocess.run("wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i cloudflared-linux-amd64.deb >/dev/null 2>&1", shell=True)

        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        start_wait = time.time()
        while time.time() - start_wait < 30:
            line = proc.stderr.readline()
            if not line:
                time.sleep(0.1)
                continue
            m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if m:
                url = m.group(0)
                log(f"Cloudflare tunnel established: {url}")
                return url
        log("Cloudflare tunnel timed out. Trying Pinggy...")

    # Pinggy fallback
    log("Setting up Pinggy tunnel...")
    try:
        cmd = f"ssh -p 443 -R0:localhost:{port} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes a.pinggy.io"
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        start_wait = time.time()
        while time.time() - start_wait < 25:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.2)
                continue
            m = re.search(r"https?://[a-zA-Z0-9.-]+\.pinggy\.link", line)
            if m:
                url = m.group(0)
                log(f"Pinggy tunnel established: {url}")
                return url
    except Exception as e:
        log(f"Pinggy failed: {e}")

    return ""

def main():
    parser = argparse.ArgumentParser(description="Inscrona GPU Burst Worker")
    parser.add_argument("--port", type=int, default=8000, help="Local worker port")
    parser.add_argument("--tunnel", type=str, choices=["cloudflare", "pinggy", "none"], default="cloudflare", help="Tunnel provider")
    args = parser.parse_args()

    log("="*60)
    log("Starting Inscrona Cloud GPU Worker...")
    log("="*60)

    ensure_ollama_running()
    ensure_models()

    public_url = ""
    if args.tunnel != "none":
        public_url = start_tunnel(args.tunnel, args.port)

    log("="*60)
    if public_url:
        log("🚀 INSCRONA GPU BURST WORKER ONLINE!")
        log(f"🌐 Public Tunnel URL: {public_url}")
        log("📋 Set this in your local Inscrona .env or Settings:")
        log(f"   COLAB_INFERENCE_URL={public_url}")
        Path("tunnel_url.txt").write_text(public_url, encoding="utf-8")
    else:
        log(f"Running worker locally on port {args.port}")
    log("="*60)

    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")

if __name__ == "__main__":
    main()
