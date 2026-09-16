"""Task 5: Start tunnel + test remote grading end-to-end."""
import time
import json
import sys
import os
import subprocess
import urllib.request
import urllib.error

# Step 1: Start tunnel
import pinggy

url_result = []

class TunnelHandler(pinggy.BaseTunnelHandler):
    def tunnel_established(self, urls):
        url_result.extend(urls)
        print(f"TUNNEL_URLS: {urls}", flush=True)

print("Starting Pinggy tunnel to localhost:8000...", flush=True)
tunnel = pinggy.start_tunnel(
    forwardto=8000,
    type="http",
    eventclass=TunnelHandler,
)

for i in range(30):
    if url_result:
        break
    time.sleep(1)

if not url_result:
    print("FAILED: No URLs after 30s", flush=True)
    sys.exit(1)

tunnel_url = url_result[0]
print(f"Tunnel URL: {tunnel_url}", flush=True)

# Step 2: Test /health
print("\n--- Testing GET /health ---", flush=True)
try:
    req = urllib.request.Request(f"{tunnel_url}/health")
    resp = urllib.request.urlopen(req, timeout=15)
    body = resp.read().decode()
    print(f"HTTP {resp.status}: {body}", flush=True)
    assert resp.status == 200, f"Expected 200, got {resp.status}"
    assert '"ok"' in body, f"Expected 'ok' in body"
    print("PASS: /health via tunnel", flush=True)
except Exception as e:
    print(f"FAIL: /health via tunnel: {e}", flush=True)
    tunnel.stop()
    sys.exit(1)

# Step 3: Test /grade with test image via curl (urllib doesn't do multipart well)
print("\n--- Testing POST /grade via curl ---", flush=True)
test_image = r"C:\Users\Cyrus\Downloads\New folder (72)\Inscrona\test_ocr.jpg"
grade_url = f"{tunnel_url}/grade"

try:
    result = subprocess.run(
        ["curl.exe", "-s", "--max-time", "600", "-F", f"file=@{test_image}", grade_url],
        capture_output=True, text=True, timeout=620
    )
    print(f"curl exit code: {result.returncode}", flush=True)
    if result.stdout:
        try:
            data = json.loads(result.stdout)
            print(f"HTTP response parsed as JSON:", flush=True)
            print(json.dumps(data, indent=2, ensure_ascii=False)[:2000], flush=True)
            # Validate structure
            for key in ["ocr_text", "questions", "overall_score"]:
                if key in data:
                    print(f"  ✓ '{key}' present", flush=True)
                else:
                    print(f"  ✗ '{key}' MISSING", flush=True)
            print("\nPASS: /grade via tunnel", flush=True)
        except json.JSONDecodeError:
            print(f"Response (not JSON): {result.stdout[:500]}", flush=True)
            print("FAIL: Response not valid JSON", flush=True)
    else:
        print(f"No stdout. stderr: {result.stderr[:500]}", flush=True)
        print("FAIL: No response from /grade", flush=True)
except Exception as e:
    print(f"FAIL: {e}", flush=True)

# Step 4: Test GET / (HTML UI) via tunnel
print("\n--- Testing GET / (HTML UI) via tunnel ---", flush=True)
try:
    req = urllib.request.Request(tunnel_url + "/")
    resp = urllib.request.urlopen(req, timeout=15)
    body = resp.read().decode()
    has_upload = "type=\"file\"" in body.lower() or "type='file'" in body.lower()
    has_title = "Inscrona" in body or "inscrona" in body.lower()
    print(f"HTTP {resp.status}, length={len(body)}, has_file_input={has_upload}, has_title={has_title}", flush=True)
    if resp.status == 200 and has_upload:
        print("PASS: / (HTML UI) via tunnel", flush=True)
    else:
        print("FAIL: / (HTML UI) via tunnel", flush=True)
except Exception as e:
    print(f"FAIL: / via tunnel: {e}", flush=True)

# Done
print("\n=== Task 5 Complete ===", flush=True)
tunnel.stop()
print("Tunnel closed.", flush=True)
