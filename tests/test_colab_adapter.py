"""Colab fallback contract tests — mocked, no Ollama/GPU/network needed.

Run: <venv python> tests/test_colab_adapter.py
"""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))


def test_normalize_legacy():
    d = main._load_dotenv  # exists
    out = asyncio.run(main._normalize_colab_result({
        "marks": 7, "confidence": 0.8,
        "feedback": "Good.", "ocr_text": "Q1 text",
    }))
    check("legacy marks->total_marks", out["total_marks"] == 7)
    check("legacy confidence->overall_confidence", out["overall_confidence"] == 0.8)
    check("legacy confidence_level high", out["confidence_level"] == "high")
    check("legacy max_total_marks default", out["max_total_marks"] == 10)
    check("legacy flags marker", "colab_legacy_schema" in out["flags"])
    check("legacy fallback_used", out["fallback_used"] is True)
    check("legacy ocr preserved", out["ocr_text"] == "Q1 text")


def test_normalize_bands():
    low = asyncio.run(main._normalize_colab_result({"marks": 2, "confidence": 0.2}))
    mid = asyncio.run(main._normalize_colab_result({"marks": 5, "confidence": 0.5}))
    check("low band", low["confidence_level"] == "low")
    check("mid band", mid["confidence_level"] == "medium")
    bad = asyncio.run(main._normalize_colab_result({"marks": 1, "confidence": "85%"}))
    check("string confidence coerced", bad["overall_confidence"] == 0.5)


def test_normalize_passthrough():
    src = {"total_marks": 8, "overall_confidence": 0.9, "feedback": "x"}
    out = asyncio.run(main._normalize_colab_result(dict(src)))
    check("new-schema total kept", out["total_marks"] == 8)
    check("new-schema conf kept", out["overall_confidence"] == 0.9)
    check("new-schema no legacy flag", "colab_legacy_schema" not in out["flags"])
    try:
        asyncio.run(main._normalize_colab_result("nope"))
        check("non-dict raises", False)
    except ValueError:
        check("non-dict raises", True)


def test_dotenv_loader():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / ".env"
        p.write_text(
            "# comment\nINSCROMA_TEST_KEY=hello123\nQUOTED='a b'\n"
            "EMPTY=\nNOEQUALS\n", encoding="utf-8",
        )
        os.environ.pop("INSCROMA_TEST_KEY", None)
        main._load_dotenv(str(p))
        check("dotenv loads key", os.getenv("INSCROMA_TEST_KEY") == "hello123")
        check("dotenv strips quotes", os.getenv("QUOTED") == "a b")
        os.environ["INSCROMA_TEST_KEY"] = "keep"
        main._load_dotenv(str(p))
        check("dotenv never overrides", os.getenv("INSCROMA_TEST_KEY") == "keep")
        for k in ("INSCROMA_TEST_KEY", "QUOTED", "EMPTY"):
            os.environ.pop(k, None)
    main._load_dotenv("/nonexistent/path/.env")  # must not raise
    check("dotenv missing file ok", True)


def test_fallback_no_colab():
    orig_gen, orig_url = main._ollama_generate, main.COLAB_INFERENCE_URL
    try:
        def boom(*a, **k):
            raise ConnectionError("ollama down")
        main._ollama_generate = boom
        main.COLAB_INFERENCE_URL = ""
        try:
            asyncio.run(main._grade_with_fallback("aGk=", "rubric", "testjob"))
            check("fallback raises with no colab", False)
        except RuntimeError as e:
            check("fallback raises with no colab", "no Colab fallback" in str(e), str(e)[:80])
    finally:
        main._ollama_generate, main.COLAB_INFERENCE_URL = orig_gen, orig_url


CANNED_GRADE_JSON = json.dumps({
    "total_marks": 8, "max_total_marks": 10, "percentage": 80.0,
    "overall_confidence": 0.8, "confidence_level": "high",
    "feedback": "mocked ok",
})


def _fake_local_ok(model, *a, **k):
    if model == "glm-ocr":
        return "Mocked OCR transcript with enough characters to pass quality gates."
    return CANNED_GRADE_JSON


async def _healthy():
    return True


async def _dead():
    return False


async def _fake_colab_ok(image_b64, rubric):
    return {"marks": 9, "confidence": 0.9, "feedback": "burst ok",
            "ocr_text": "burst ocr text"}


def test_routing_matrix():
    o_gen, o_health, o_ep, o_url = (
        main._ollama_generate, main._colab_healthy,
        main._colab_grade_endpoint, main.COLAB_INFERENCE_URL,
    )
    try:
        main._ollama_generate = _fake_local_ok
        main._colab_healthy = _healthy
        main._colab_grade_endpoint = _fake_colab_ok
        main.COLAB_INFERENCE_URL = "http://mocked-colab/"
        # (a) default: local-first, no burst flags
        r = asyncio.run(main._grade_with_fallback("aGk=", "r", "jA"))
        check("route default local", r["fallback_used"] is False
              and "burst_unavailable" not in r.get("flags", []))
        # (b) burst + healthy colab: colab primary
        r = asyncio.run(main._grade_with_fallback("aGk=", "r", "jB", burst=True))
        check("route burst healthy colab", r["fallback_used"] is True
              and r["total_marks"] == 9)
        gr = main.GradeResult(**{"job_id": "jB", "processing_time_ms": 1,
                                 "percentage": 90.0, **r})
        check("burst result validates", gr.total_marks == 9)
        # (c) burst + dead colab: local + burst_unavailable flag (never 500)
        main._colab_healthy = _dead
        r = asyncio.run(main._grade_with_fallback("aGk=", "r", "jC", burst=True))
        check("route burst dead local", r["fallback_used"] is False
              and "burst_unavailable" in r.get("flags", []))
    finally:
        (main._ollama_generate, main._colab_healthy,
         main._colab_grade_endpoint, main.COLAB_INFERENCE_URL) = (
            o_gen, o_health, o_ep, o_url)


def test_health_timeout_fast():
    o_url, o_t = main.COLAB_INFERENCE_URL, main.COLAB_HEALTH_TIMEOUT_S
    try:
        main.COLAB_INFERENCE_URL = "http://10.255.255.1/"
        main.COLAB_HEALTH_TIMEOUT_S = 1
        t0 = time.perf_counter()
        ok = asyncio.run(main._colab_healthy())
        dt = time.perf_counter() - t0
        check("health dead fast", ok is False and dt < 5, f"{dt:.1f}s")
    finally:
        main.COLAB_INFERENCE_URL, main.COLAB_HEALTH_TIMEOUT_S = o_url, o_t


def test_overlap_not_serialized():
    o_gen = main._ollama_generate
    try:
        def slow(model, *a, **k):
            time.sleep(10)
            return ("slow ocr text here" if model == "glm-ocr"
                    else CANNED_GRADE_JSON)
        main._ollama_generate = slow

        async def both():
            return await asyncio.gather(
                main._grade_with_fallback("aGk=", "r", "jobA"),
                main._grade_with_fallback("aGk=", "r", "jobB"),
            )
        t0 = time.perf_counter()
        out = asyncio.run(both())
        dt = time.perf_counter() - t0
        print(f"overlap wall clock: {dt:.1f}s (serialized would be ~40s)")
        check("overlap wall ~20s", dt < 32, f"{dt:.1f}s")
        check("overlap both ok", out[0]["total_marks"] == 8
              and out[1]["total_marks"] == 8)
    finally:
        main._ollama_generate = o_gen


def test_breaker_transitions():
    main._breaker_reset()
    check("breaker starts closed", main._breaker_allows() is True)
    main._breaker_failure()
    main._breaker_failure()
    check("breaker closed after 2", main._colab_breaker["state"] == "CLOSED")
    opened = main._breaker_failure()
    check("breaker opens on 3rd", opened is True
          and main._breaker_allows() is False)
    main._colab_breaker["opened_at"] -= 61
    check("breaker half-open after cooldown", main._breaker_allows() is True
          and main._colab_breaker["state"] == "HALF-OPEN")
    main._breaker_success()
    check("breaker resets on success", main._colab_breaker["state"] == "CLOSED"
          and main._colab_breaker["failures"] == 0)


def test_breaker_open_instant_skip():
    o_gen, o_health, o_ep = (
        main._ollama_generate, main._colab_healthy, main._colab_grade_endpoint)
    try:
        main._breaker_reset()
        main._ollama_generate = _fake_local_ok
        main._colab_healthy = _healthy  # would succeed if consulted

        def must_not_run(*a, **k):
            raise AssertionError("Colab must be skipped while breaker OPEN")
        main._colab_grade_endpoint = must_not_run
        main._breaker_failure()
        main._breaker_failure()
        main._breaker_failure()
        r = asyncio.run(main._grade_with_fallback("aGk=", "r", "jD", burst=True))
        flags = r.get("flags", [])
        check("open instant local", r["fallback_used"] is False)
        check("open flags set", "burst_unavailable" in flags
              and "colab_circuit_open" in flags, str(flags))
    finally:
        main._breaker_reset()
        (main._ollama_generate, main._colab_healthy,
         main._colab_grade_endpoint) = (o_gen, o_health, o_ep)


def test_warm_prime_and_unload():
    o_gen, o_health, o_ep, o_unload = (
        main._ollama_generate, main._colab_healthy,
        main._colab_grade_endpoint, main._colab_unload_models)
    calls = {"healthy": 0, "unload": 0, "endpoint": 0}
    try:
        main._breaker_reset()
        main._ollama_generate = _fake_local_ok

        async def counting_healthy():
            calls["healthy"] += 1
            return True
        main._colab_healthy = counting_healthy

        async def counting_ep(image_b64, rubric):
            calls["endpoint"] += 1
            return await _fake_colab_ok(image_b64, rubric)
        main._colab_grade_endpoint = counting_ep

        async def counting_unload():
            calls["unload"] += 1
        main._colab_unload_models = counting_unload

        r = asyncio.run(main._grade_with_fallback(
            "aGk=", "r", "jE", burst=True, warm=True))
        check("warm prime probed", calls["healthy"] >= 2, str(calls))
        check("warm endpoint once", calls["endpoint"] == 1, str(calls))
        check("warm unload called", calls["unload"] == 1, str(calls))
        check("warm flag set", "warmed" in r.get("flags", []))
        check("warm colab result", r["fallback_used"] is True
              and r["total_marks"] == 9)
    finally:
        main._breaker_reset()
        (main._ollama_generate, main._colab_healthy,
         main._colab_grade_endpoint, main._colab_unload_models) = (
            o_gen, o_health, o_ep, o_unload)


def test_local_failure_breaker_open():
    o_gen, o_ep, o_url = (
        main._ollama_generate, main._colab_grade_endpoint,
        main.COLAB_INFERENCE_URL)
    try:
        main._breaker_reset()
        main._breaker_failure()
        main._breaker_failure()
        main._breaker_failure()

        def boom(*a, **k):
            raise ConnectionError("ollama down")
        main._ollama_generate = boom

        def must_not_run(*a, **k):
            raise AssertionError("Colab must be skipped while breaker OPEN")
        main._colab_grade_endpoint = must_not_run
        main.COLAB_INFERENCE_URL = "http://mocked-colab/"
        try:
            asyncio.run(main._grade_with_fallback("aGk=", "r", "jF"))
            check("open failure raises", False)
        except RuntimeError as e:
            check("open failure raises", "circuit OPEN" in str(e), str(e)[:90])
    finally:
        main._breaker_reset()
        (main._ollama_generate, main._colab_grade_endpoint,
         main.COLAB_INFERENCE_URL) = (o_gen, o_ep, o_url)


def test_health_mode_field():
    from fastapi.testclient import TestClient
    main._breaker_reset()
    c = TestClient(main.app)
    r = c.get("/health")
    body = r.json()
    check("health mode local-only", r.status_code == 200
          and body.get("mode") == "local-only"
          and body.get("colab_circuit_open") is False, str(body))
    main._breaker_failure()
    main._breaker_failure()
    main._breaker_failure()
    body = c.get("/health").json()
    check("health mode open flag", body.get("colab_circuit_open") is True
          and body.get("mode") == "local-only", str(body))
    main._breaker_reset()


if __name__ == "__main__":
    test_normalize_legacy()
    test_normalize_bands()
    test_normalize_passthrough()
    test_dotenv_loader()
    test_fallback_no_colab()
    test_routing_matrix()
    test_health_timeout_fast()
    test_overlap_not_serialized()
    test_breaker_transitions()
    test_breaker_open_instant_skip()
    test_warm_prime_and_unload()
    test_local_failure_breaker_open()
    test_health_mode_field()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
