"""Unit tests for Cryptographic Tamper-Evident Audit Trail and Psychometric Analytics."""
import json
import pytest
from app.audit import (
    append_audit_event,
    verify_chain_integrity,
    compute_class_analytics,
)


def test_audit_chain_append_and_verify(tmp_path):
    log_path = tmp_path / "audit_chain.jsonl"

    # Append 3 events
    rec1 = append_audit_event("sub_001", 18.5, 20.0, action="EVALUATE", log_path=log_path)
    assert rec1["previous_hash"] == "GENESIS_ROOT_00000000000000000000000000000000000000000000000000000000"
    assert len(rec1["entry_hash"]) == 64

    rec2 = append_audit_event("sub_002", 14.0, 20.0, action="EVALUATE", log_path=log_path)
    assert rec2["previous_hash"] == rec1["entry_hash"]

    rec3 = append_audit_event("sub_001", 19.5, 20.0, action="OVERRIDE", actor="PROF_CYRUS", notes="Recalibrated Q2", log_path=log_path)
    assert rec3["previous_hash"] == rec2["entry_hash"]

    # Verify chain passes
    is_valid, count, error = verify_chain_integrity(log_path=log_path)
    assert is_valid is True
    assert count == 3
    assert error is None


def test_audit_chain_detects_tampering(tmp_path):
    log_path = tmp_path / "tampered_audit.jsonl"

    append_audit_event("sub_001", 12.0, 20.0, log_path=log_path)
    append_audit_event("sub_002", 15.0, 20.0, log_path=log_path)

    # Tamper with record 1 (illegally inflate score from 12.0 to 20.0)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    tampered_rec = json.loads(lines[0])
    tampered_rec["total_awarded"] = 20.0
    lines[0] = json.dumps(tampered_rec)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Verify must catch the tampering!
    is_valid, count, error = verify_chain_integrity(log_path=log_path)
    assert is_valid is False
    assert "Tampered record" in error


def test_class_analytics_computation():
    submissions = [
        {"grading": {"total_awarded": 18.0, "total_max": 20.0, "grades": [{"question_id": "Q1", "awarded_marks": 5.0, "max_marks": 5.0}]}},
        {"grading": {"total_awarded": 16.0, "total_max": 20.0, "grades": [{"question_id": "Q1", "awarded_marks": 4.0, "max_marks": 5.0}]}},
        {"grading": {"total_awarded": 14.0, "total_max": 20.0, "grades": [{"question_id": "Q1", "awarded_marks": 3.0, "max_marks": 5.0}]}},
        {"grading": {"total_awarded": 6.0, "total_max": 20.0, "grades": [{"question_id": "Q1", "awarded_marks": 1.0, "max_marks": 5.0}]}},
    ]
    analytics = compute_class_analytics(submissions)
    assert analytics["count"] == 4
    assert analytics["mean"] == 13.5
    assert analytics["median"] == 15.0
    assert analytics["std_dev"] > 0
    assert analytics["pass_rate"] == 75.0  # 3 of 4 >= 8.0/20.0
    assert "Q1" in analytics["question_difficulty"]
    assert "Q1" in analytics["question_discrimination"]
