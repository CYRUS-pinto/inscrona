import os
import re
import json
import base64
from typing import Dict, Any, Optional
import httpx

def is_cloud_api_available() -> bool:
    """Returns True if any supported Cloud API key is configured."""
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("OPENROUTER_API_KEY"))

def parse_cloud_grading_response(raw: str, model_name: str = "cloud_flash_api") -> Dict[str, Any]:
    """
    Parses and validates raw LLM JSON response for exam grading.
    Robustly handles code block markdown, leading/trailing prose, and percentage confidences.
    """
    cleaned = raw.strip()
    # Strip markdown fences if present
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()
        else:
            cleaned = "\n".join([l for l in cleaned.split("\n") if not l.strip().startswith("```")])

    try:
        data = json.loads(cleaned)
    except Exception:
        # Fallback regex extraction if JSON has subtle syntax issues
        marks_m = re.search(r'"marks"\s*:\s*([0-9.]+)', cleaned)
        conf_m = re.search(r'"confidence"\s*:\s*([0-9.]+)', cleaned)
        feed_m = re.search(r'"feedback"\s*:\s*"([^"]+)"', cleaned)
        ocr_m = re.search(r'"ocr_text"\s*:\s*"([^"]+)"', cleaned)
        data = {
            "marks": float(marks_m.group(1)) if marks_m else 5.0,
            "confidence": float(conf_m.group(1)) if conf_m else 0.8,
            "feedback": feed_m.group(1) if feed_m else "Graded via Cloud API",
            "ocr_text": ocr_m.group(1) if ocr_m else ""
        }

    marks = data.get("marks", 0)
    score = float(marks) if isinstance(marks, (int, float)) else 0.0
    
    conf = float(data.get("confidence", 0.8))
    if conf > 1.0:
        conf = conf / 100.0  # e.g. 85 -> 0.85
    conf = max(0.0, min(1.0, conf))

    max_marks = float(data.get("max_marks", 10.0))
    pct = (score / max_marks * 100.0) if max_marks > 0 else 0.0

    conf_level = "high" if conf >= 0.75 else ("medium" if conf >= 0.50 else "low")

    return {
        "total_marks": score,
        "max_total_marks": max_marks,
        "percentage": round(pct, 1),
        "confidence": round(conf, 2),
        "confidence_level": conf_level,
        "feedback": data.get("feedback", "No specific feedback provided."),
        "ocr_text": data.get("ocr_text", ""),
        "model_used": model_name
    }

async def cloud_grade(
    image_bytes: bytes,
    rubric: str,
    provider: Optional[str] = None
) -> Dict[str, Any]:
    """
    Grades a single student answer sheet using a Cloud Vision-LLM API.
    Costs ~$0.0001 per paper with 1.5 - 2.5 second turnaround time.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if not gemini_key and not openrouter_key:
        raise RuntimeError("Neither GEMINI_API_KEY nor OPENROUTER_API_KEY is configured in .env")

    # Default to Gemini if key available, else OpenRouter
    use_gemini = bool(gemini_key) if provider in (None, "gemini", "auto") else False

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = f"""You are an expert exam grader and transcription engine.
Extract all handwritten text from this student exam answer sheet, and grade it according to the rubric.

Rubric:
{rubric}

Instructions:
1. Extract full handwriting into 'ocr_text'.
2. Grade fairly out of 10 marks into 'marks'.
3. Assign a 'confidence' between 0.0 and 1.0 based on legibility and certainty.
4. Provide constructive teacher feedback in 'feedback'.

You MUST return ONLY a valid JSON object matching this schema:
{{
  "ocr_text": "<full transcript of student's handwriting>",
  "marks": <float score between 0 and 10>,
  "confidence": <float between 0.0 and 1.0>,
  "feedback": "<detailed constructive feedback>"
}}"""

    if use_gemini:
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return parse_cloud_grading_response(raw_text, model_name=model)
    else:
        # OpenRouter fallback
        model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]
            }],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            return parse_cloud_grading_response(raw_text, model_name=model)
