import pytest
from cloud_api import parse_cloud_grading_response, is_cloud_api_available

def test_cloud_response_parsing_clean_json():
    raw_json = '{"marks": 9, "confidence": 0.95, "feedback": "Excellent work with clear derivations", "ocr_text": "Q1: Photosynthesis..."}'
    res = parse_cloud_grading_response(raw_json, model_name="mistral/pixtral-12b-2409")
    assert res["total_marks"] == 9.0
    assert res["max_total_marks"] == 10.0
    assert res["percentage"] == 90.0
    assert res["confidence"] == 0.95
    assert res["confidence_level"] == "high"
    assert res["feedback"] == "Excellent work with clear derivations"
    assert res["ocr_text"] == "Q1: Photosynthesis..."
    assert res["model_used"] == "mistral/pixtral-12b-2409"

def test_cloud_response_parsing_markdown_wrapped_json():
    raw_json = """```json
    {
        "marks": 6.5,
        "confidence": 65,
        "feedback": "Partial credit awarded for step 2",
        "ocr_text": "Answer 2: The velocity is 5m/s"
    }
    ```"""
    res = parse_cloud_grading_response(raw_json)
    assert res["total_marks"] == 6.5
    assert res["confidence"] == 0.65
    assert res["confidence_level"] == "medium"
    assert "Partial credit" in res["feedback"]

def test_cloud_api_availability(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert is_cloud_api_available() is False

    monkeypatch.setenv("MISTRAL_API_KEY", "mistral_test_key_xyz")
    assert is_cloud_api_available() is True
