"""Task 2: Sequential OCR → Grading pipeline with keep_alive: 0 unloading."""
import json
import requests
import subprocess
import time
import sys

OLLAMA = "http://localhost:11434"
IMAGE_PATH = r"C:\Users\Cyrus\Downloads\New folder (72)\Inscrona\test_ocr.jpg"

def ollama_generate(model, prompt, images=None, keep_alive=0, format_json=False):
    """Call Ollama /api/generate with streaming, return full response text."""
    payload = {
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
    resp = requests.post(f"{OLLAMA}/api/generate", json=payload, stream=True, timeout=600)
    full = []
    for line in resp.iter_lines():
        if line:
            chunk = json.loads(line)
            token = chunk.get("response", "")
            full.append(token)
            if chunk.get("done"):
                break
    elapsed = time.time() - start
    return "".join(full), elapsed

def get_running():
    """Return ollama ps output."""
    result = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=10)
    return result.stdout.strip()

def main():
    print("=" * 60)
    print("STEP 0: Check initial state (ollama ps)")
    print("=" * 60)
    ps = get_running()
    print(f"ollama ps:\n{ps}\n")

    # ── Step 1: OCR ──
    print("=" * 60)
    print("STEP 1: Run glm-ocr on test image")
    print("=" * 60)
    with open(IMAGE_PATH, "rb") as f:
        image_b64 = [__import__("base64").b64encode(f.read()).decode()]

    ocr_prompt = "Extract all text from this answer booklet image. Output only the text content, nothing else."
    ocr_text, ocr_time = ollama_generate("glm-ocr", ocr_prompt, images=image_b64, keep_alive=0)
    print(f"OCR completed in {ocr_time:.1f}s")
    print(f"OCR output ({len(ocr_text)} chars):\n{ocr_text[:1000]}{'...' if len(ocr_text) > 1000 else ''}\n")

    # ── Step 2: Unload OCR model ──
    print("=" * 60)
    print("STEP 2: Unload glm-ocr (keep_alive: 0)")
    print("=" * 60)
    requests.post(f"{OLLAMA}/api/generate", json={
        "model": "glm-ocr", "keep_alive": 0, "prompt": ""
    }, timeout=30)
    time.sleep(3)
    ps = get_running()
    print(f"ollama ps after OCR unload:\n{ps}\n")

    # ── Step 3: Grade with llama3.2:3b ──
    print("=" * 60)
    print("STEP 3: Grade with llama3.2:3b (format=json)")
    print("=" * 60)
    grading_prompt = f"""You are an exam grading assistant. Grade the following student answer.

Student Answer:
{ocr_text}

Rubric: Rate the answer on a scale of 0-10 for content accuracy, completeness, and clarity.

Respond ONLY with valid JSON in this exact format:
{{"marks": <0-10>, "confidence": <0.0-1.0>, "feedback": "<brief assessment>"}}
"""
    grade_text, grade_time = ollama_generate("llama3.2:3b", grading_prompt, keep_alive=0, format_json=True)
    print(f"Grading completed in {grade_time:.1f}s")
    print(f"Raw grading output:\n{grade_text}\n")

    # ── Step 4: Parse and validate JSON ──
    print("=" * 60)
    print("STEP 4: Validate JSON output")
    print("=" * 60)
    try:
        # Strip markdown fences if present
        cleaned = grade_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            cleaned = "\n".join(lines)
        parsed = json.loads(cleaned)
        required_keys = ["marks", "confidence", "feedback"]
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            print(f"VALIDATION FAILED: Missing keys: {missing}")
            sys.exit(1)
        marks = parsed["marks"]
        confidence = parsed["confidence"]
        feedback = parsed["feedback"]
        print(f"marks: {marks} ({type(marks).__name__})")
        print(f"confidence: {confidence} ({type(confidence).__name__})")
        print(f"feedback: {feedback}")
        assert isinstance(marks, (int, float)), "marks must be numeric"
        assert isinstance(confidence, (int, float)), "confidence must be numeric"
        assert isinstance(feedback, str), "feedback must be string"
        print("JSON VALIDATION PASSED")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"VALIDATION FAILED: {e}")
        sys.exit(1)

    # ── Step 5: Unload grading model ──
    print("\n" + "=" * 60)
    print("STEP 5: Unload llama3.2:3b (keep_alive: 0)")
    print("=" * 60)
    requests.post(f"{OLLAMA}/api/generate", json={
        "model": "llama3.2:3b", "keep_alive": 0, "prompt": ""
    }, timeout=30)
    time.sleep(3)
    ps = get_running()
    print(f"ollama ps after grading unload:\n{ps}\n")

    if ps and ("llama" in ps.lower() or "glm" in ps.lower()):
        print("WARNING: Models still running after unload!")
        print(f"Full output:\n{grade_text}")
        sys.exit(1)

    print("=" * 60)
    print("TASK 2 COMPLETE: Sequential OCR → Grading pipeline verified")
    print("=" * 60)

if __name__ == "__main__":
    main()
