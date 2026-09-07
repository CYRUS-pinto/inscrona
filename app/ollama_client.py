"""
Ollama client with SSRF-safe URL validation and connection management.
"""

import httpx
from typing import Optional

from . import config


def _validate_url(url: str) -> str:
    """Validate URL is safe (loopback/private only for local Ollama)."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    # Allow loopback and private ranges
    import ipaddress
    try:
        ip = ipaddress.ip_address(hostname)
        if not (ip.is_loopback or ip.is_private or ip.is_reserved):
            raise ValueError(f"SSRF blocked: {hostname} is not a private/loopback address")
    except ValueError:
        # Not an IP — could be hostname like 'localhost'
        if hostname not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            # Check if it resolves to private
            import socket
            try:
                resolved = socket.gethostbyname(hostname)
                resolved_ip = ipaddress.ip_address(resolved)
                if not (resolved_ip.is_loopback or resolved_ip.is_private or resolved_ip.is_reserved):
                    raise ValueError(f"SSRF blocked: {hostname} resolves to {resolved} which is not private")
            except (socket.gaierror, ValueError) as e:
                if "SSRF" in str(e):
                    raise
                # DNS resolution failure — allow it (might be local hostname)
                pass
    return url


def _get_client() -> httpx.Client:
    """Create a validated httpx client pointing at local Ollama."""
    base_url = _validate_url(config.OLLAMA_HOST)
    return httpx.Client(
        base_url=base_url,
        follow_redirects=False,
        trust_env=False,
        timeout=config.GRADE_TIMEOUT_S,
    )


def chat(
    model: str,
    messages: list[dict],
    keep_alive: str = "30m",
    timeout_s: Optional[int] = None,
    options: Optional[dict] = None,
) -> dict:
    """Send a chat completion request to Ollama."""
    timeout = timeout_s or config.GRADE_TIMEOUT_S
    payload = {
        "model": model,
        "messages": messages,
        "keep_alive": keep_alive,
        "stream": False,
    }
    if options:
        payload["options"] = options

    with httpx.Client(
        base_url=_validate_url(config.OLLAMA_HOST),
        follow_redirects=False,
        trust_env=False,
        timeout=timeout,
    ) as client:
        resp = client.post("/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()


def pull_model(model: str, timeout_s: int = 600) -> bool:
    """Pull a model if not present. Returns True on success."""
    try:
        with _get_client() as client:
            resp = client.post(
                "/api/pull",
                json={"name": model, "stream": False},
                timeout=timeout_s,
            )
            resp.raise_for_status()
            return True
    except Exception:
        return False


def model_exists(model: str) -> bool:
    """Check if a model is available locally."""
    try:
        with _get_client() as client:
            resp = client.get("/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return any(m.get("name", "").startswith(model) for m in models)
    except Exception:
        return False


def unload_model(model: str) -> bool:
    """Explicitly evict model from VRAM by issuing keep_alive=0 to Ollama."""
    if not model:
        return False
    try:
        with _get_client() as client:
            client.post("/api/generate", json={"model": model, "keep_alive": 0})
        return True
    except Exception:
        return False
