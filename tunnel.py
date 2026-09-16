"""Start a Pinggy tunnel to expose the local server."""
import pinggy
import time

url_result = []

class TunnelHandler(pinggy.BaseTunnelHandler):
    def tunnel_established(self, urls):
        url_result.extend(urls)
        print(f"TUNNEL_URLS: {urls}")

print("Starting Pinggy tunnel to localhost:8000...")
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
    print(f"Waiting... ({i+1}s)")

if url_result:
    print(f"\nSUCCESS: Tunnel established")
    for u in url_result:
        print(f"URL: {u}")
else:
    print("FAILED: No URLs obtained after 30s")

# Keep alive
print("\nKeeping tunnel alive for 60s...")
time.sleep(60)
tunnel.stop()
print("Tunnel closed.")
