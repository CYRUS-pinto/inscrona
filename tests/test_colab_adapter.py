"""Colab fallback contract tests — mocked, no Ollama/GPU/network needed.

Run: <venv python> tests/test_colab_adapter.py
"""
import asyncio
import os
import sys
import tempfile
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


if __name__ == "__main__":
    test_normalize_legacy()
    test_normalize_bands()
    test_normalize_passthrough()
    test_dotenv_loader()
    test_fallback_no_colab()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)
