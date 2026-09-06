"""Single gateway for every Ollama HTTP call.

All request URLs are built from OLLAMA_HOST, which is validated once here:
scheme must be http(s) and the resolved address must be loopback or a
private/LAN IP (Ollama runs on this machine or the college LAN — never public).
httpx clients are created with follow_redirects=False and no trust_env proxies
to prevent redirect/proxy-based SSRF bypasses.
"""
import ipaddress
import socket
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from . import config


class OllamaHostError(ValueError):
    pass


def _validated_base() -> str:
    parsed = urlparse(config.OLLAMA_HOST)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise OllamaHostError(
            f"OLLAMA_HOST must be an http(s) URL, got: {config.OLLAMA_HOST!r}"
        )
    host = parsed.hostname
    if host not in ("localhost",):
        try:
            addr = ipaddress.ip_address(socket.gethostbyname(host))
        except (socket.gaierror, ValueError) as exc:
            raise OllamaHostError(f"OLLAMA_HOST cannot be resolved: {host}") from exc
        if not (addr.is_loopback or addr.is_private):
            raise OllamaHostError(
                f"OLLAMA_HOST must be loopback or private/LAN, resolved to {addr}"
            )
    return config.OLLAMA_HOST.rstrip("/")


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        headers={"Accept": "application/json"},
    )


def chat(payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
    """POST to the local Ollama chat endpoint and return parsed JSON."""
    base = _validated_base()
    with _client(timeout or config.GRADE_TIMEOUT_S) as c:
        r = c.post(base + "/api/chat", json=payload)
        r.raise_for_status()
        return r.json()


def list_models() -> Tuple[bool, List[str]]:
    """Best-effort reachability probe + installed model tags."""
    try:
        base = _validated_base()
        with _client(5.0) as c:
            r = c.get(base + "/api/tags")
            r.raise_for_status()
            return True, [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        return False, []
