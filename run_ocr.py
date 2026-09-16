import base64
import json
import urllib.request

img_path = r"C:\Users\Cyrus\Downloads\New folder (72)\Inscrona\test_resized.jpg"
with open(img_path, "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

payload = json.dumps({
    "model": "glm-ocr",
    "prompt": "Read all text in this image. Output every line of text you see, preserving layout as much as possible.",
    "images": [img_b64],
    "stream": False
}).encode()

req = urllib.request.Request(
    "http://127.0.0.1:11434/api/generate",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)

print("Sending to Ollama API...")
with urllib.request.urlopen(req, timeout=300) as resp:
    result = json.loads(resp.read().decode())
    print("=== OCR OUTPUT ===")
    print(result.get("response", "NO RESPONSE"))
    print("=== DONE ===")
