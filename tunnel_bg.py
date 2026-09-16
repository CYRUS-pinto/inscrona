"""Start a Pinggy tunnel in background, print URL, keep alive 5 minutes."""
import sys
import time
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

# Wait for URLs
for i in range(30):
    if url_result:
        break
    time.sleep(1)

if url_result:
    print(f"\nSUCCESS", flush=True)
    for u in url_result:
        print(f"URL: {u}", flush=True)
    sys.stdout.flush()
else:
    print("FAILED: No URLs after 30s", flush=True)
    sys.exit(1)

# Keep alive 3 minutes
print("\nKeeping tunnel alive for 3 minutes...", flush=True)
time.sleep(180)
tunnel.stop()
print("Tunnel closed.", flush=True)
