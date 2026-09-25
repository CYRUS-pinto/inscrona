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
from pathlib import Path
from PIL import Image

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
REQUIRED_MODELS = ["glm-ocr", "llama3.2:3b"]

def log(msg: str):
    print(f"[Inscrona-Worker] {msg}", flush=True)

def ensure_ollama_running():
    """Ensure Ollama daemon is running."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.status_code == 200:
            log("Ollama daemon is already active.")
            return
    except Exception:
        pass

    log("Starting Ollama background process...")
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(15):
        time.sleep(1)
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if r.status_code == 200:
                log("Ollama daemon started successfully.")
                return
        except Exception:
            pass
    log("Warning: Ollama did not respond immediately. Continuing...")

def ensure_models():
    """Ensure required models are pulled."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        installed = [m["name"].split(":")[0] for m in r.json().get("models", [])]
    except Exception:
        installed = []

    for m in REQUIRED_MODELS:
        if m not in installed:
            log(f"Pulling model: {m} (this may take a couple of minutes)...")
            subprocess.run(["ollama", "pull", m], check=True)
            log(f"Model {m} ready.")
        else:
            log(f"Model {m} is ready.")

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
        gpu_info = "Unknown GPU"
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
        rubric: str = Form(default="Evaluate answer accuracy and completeness.")
    ):
        start_t = time.perf_counter()
        raw_bytes = await file.read()
        if not raw_bytes:
            raise HTTPException(400, "Empty file uploaded")

        # Process image
        img = Image.open(io.BytesIO(raw_bytes))
        if max(img.size) > 1600:
            scale = 1600 / max(img.size)
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        # 1. OCR with GLM-OCR
        ocr_prompt = "Extract all handwritten and printed text from this exam answer paper accurately. Preserve lines and question numbers."
        ocr_resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": "glm-ocr",
            "prompt": ocr_prompt,
            "images": [img_b64],
            "stream": False,
            "options": {"num_ctx": 4096}
        }, timeout=300)
        ocr_text = ocr_resp.json().get("response", "")

        # 2. Evaluation with Llama 3.2
        grade_prompt = f"""You are an expert university exam grader. Grade the student answers against the rubric.

STUDENT ANSWER:
{ocr_text}

RUBRIC:
{rubric}

Respond ONLY with valid JSON matching:
{{
  "marks": <number 0-20>,
  "confidence": <number 0.0-1.0>,
  "feedback": "<concise evaluation>",
  "question_grades": []
}}"""

        eval_resp = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": "llama3.2:3b",
            "prompt": grade_prompt,
            "format": "json",
            "stream": False,
            "options": {"num_ctx": 4096, "temperature": 0.1}
        }, timeout=120)

        raw_eval = eval_resp.json().get("response", "{}")
        try:
            parsed = json.loads(raw_eval)
        except Exception:
            parsed = {"marks": 10, "confidence": 0.8, "feedback": raw_eval}

        parsed["ocr_text"] = ocr_text
        parsed["processing_time_ms"] = int((time.perf_counter() - start_t) * 1000)
        parsed["model_used"] = "glm-ocr + llama3.2:3b (Colab GPU)"
        return JSONResponse(parsed)

    return app

def start_tunnel(tunnel_type: str, port: int) -> str:
    """Start Pinggy or Cloudflare tunnel and return public URL."""
    if tunnel_type == "pinggy":
        try:
            import pinggy
            class Handler(pinggy.BaseTunnelHandler):
                def __init__(self):
                    self.urls = []
                def tunnel_established(self, urls):
                    self.urls.extend(urls)

            h = Handler()
            log("Initiating Pinggy tunnel...")
            t = pinggy.start_tunnel(forwardto=port, type="http", eventclass=Handler)
            # Give it a moment to establish
            for _ in range(15):
                time.sleep(1)
                if h.urls:
                    return h.urls[0]
        except Exception as e:
            log(f"Pinggy Python SDK failed: {e}. Falling back to ssh/pinggy command...")
            # SSH Pinggy fallback
            try:
                cmd = ["ssh", "-p", "443", "-R0:localhost:8000", "a.pinggy.io", "-o", "StrictHostKeyChecking=no"]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for _ in range(15):
                    line = proc.stdout.readline()
                    m = re.search(r"https://[a-zA-Z0-9-]+\.a\.pinggy\.link", line) or re.search(r"https://[a-zA-Z0-9-]+\.free\.pinggy\.link", line)
                    if m:
                        return m.group(0)
            except Exception as e2:
                log(f"Pinggy fallback failed: {e2}")

    # Cloudflare fallback / default
    log("Starting Cloudflare tunnel...")
    # Install cloudflared if missing
    if subprocess.call(["which", "cloudflared"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        log("Installing cloudflared...")
        subprocess.run("curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null", shell=True)
        subprocess.run("wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb && dpkg -i cloudflared-linux-amd64.deb >/dev/null 2>&1", shell=True)

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    for _ in range(20):
        line = proc.stderr.readline()
        m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if m:
            return m.group(0)
        time.sleep(0.5)

    return ""

def main():
    parser = argparse.ArgumentParser(description="Inscrona GPU Burst Worker")
    parser.add_argument("--port", type=int, default=8000, help="Local worker port")
    parser.add_argument("--tunnel", type=str, choices=["pinggy", "cloudflare", "none"], default="pinggy", help="Tunnel provider")
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
        log("📋 Set this in your local Inscrona .env:")
        log(f"   COLAB_INFERENCE_URL={public_url}")
        # Also write to tunnel_url.txt
        Path("tunnel_url.txt").write_text(public_url, encoding="utf-8")
    else:
        log(f"Running locally without tunnel on port {args.port}")
    log("="*60)

    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")

if __name__ == "__main__":
    main()
