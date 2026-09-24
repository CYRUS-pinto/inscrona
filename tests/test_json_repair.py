import json
import re
import pytest

def repair_json_string(cleaned: str) -> dict:
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        repaired = cleaned
        repaired = re.sub(r'("[^"\n]*")\s*\n\s*("([a-zA-Z0-9_]+)"\s*:)', r'\1,\n\2', repaired)
        repaired = re.sub(r'([\d\.]+|true|false)\s*\n\s*("[\w_]+"\s*:)', r'\1,\n\2', repaired)
        repaired = re.sub(r'(\}\s*)\n(\s*\{)', r'\1,\n\2', repaired)
        repaired = re.sub(r',\s*([\}\]])', r'\1', repaired)
        open_braces = repaired.count('{') - repaired.count('}')
        open_brackets = repaired.count('[') - repaired.count(']')
        if open_brackets > 0:
            repaired += ']' * open_brackets
        if open_braces > 0:
            repaired += '}' * open_braces
        return json.loads(repaired)

def test_missing_comma_strings():
    raw = '''{
        "feedback": "Well done."
        "confidence_level": "high"
    }'''
    res = repair_json_string(raw)
    assert res["feedback"] == "Well done."
    assert res["confidence_level"] == "high"

def test_missing_comma_numbers_and_booleans():
    raw = '''{
        "total_marks": 18.5
        "passed": true
        "percentage": 92.5
    }'''
    res = repair_json_string(raw)
    assert res["total_marks"] == 18.5
    assert res["passed"] is True
    assert res["percentage"] == 92.5

def test_missing_comma_in_list_of_objects():
    raw = '''{
        "questions": [
            {"num": 1, "marks": 5}
            {"num": 2, "marks": 5}
        ]
    }'''
    res = repair_json_string(raw)
    assert len(res["questions"]) == 2
    assert res["questions"][1]["marks"] == 5

def test_trailing_commas():
    raw = '''{
        "total_marks": 20,
        "questions": [1, 2, ],
    }'''
    res = repair_json_string(raw)
    assert res["total_marks"] == 20
    assert res["questions"] == [1, 2]

def test_unclosed_truncation():
    raw = '''{
        "total_marks": 20,
        "items": [
            {"id": 1}'''
    res = repair_json_string(raw)
    assert res["total_marks"] == 20
    assert res["items"][0]["id"] == 1
